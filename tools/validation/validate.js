/**
 * Planetary Health Knowledge Graph - Data Validation Script
 * 
 * This script validates data against the JSON schemas defined for the
 * Planetary Health Knowledge Graph. It can be used to validate data
 * before importing it into the database.
 */

const fs = require('fs');
const path = require('path');
const Ajv = require('ajv');
const addFormats = require('ajv-formats');
const chalk = require('chalk');

// Initialize Ajv
const ajv = new Ajv({
  allErrors: true,
  verbose: true,
  $data: true
});
addFormats(ajv);

// Load schemas
const schemaDir = path.join(__dirname, '../../schema/json-schema');
const schemas = {};

// Load all schema files
const schemaFiles = fs.readdirSync(schemaDir).filter(file => file.endsWith('.json'));
schemaFiles.forEach(file => {
  const schemaName = path.basename(file, '.json');
  const schemaPath = path.join(schemaDir, file);
  const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
  schemas[schemaName] = schema;
  ajv.addSchema(schema, schemaName);
});

/**
 * Validates a single entity against its schema
 * @param {Object} entity - The entity to validate
 * @param {string} schemaName - The name of the schema to validate against
 * @returns {Object} - Validation result with success flag and errors
 */
function validateEntity(entity, schemaName) {
  if (!schemas[schemaName]) {
    return {
      success: false,
      errors: [`Schema "${schemaName}" not found`]
    };
  }

  const validate = ajv.getSchema(schemaName);
  const valid = validate(entity);

  if (valid) {
    return {
      success: true,
      errors: []
    };
  } else {
    return {
      success: false,
      errors: validate.errors.map(error => {
        return {
          path: error.instancePath,
          message: error.message,
          params: error.params
        };
      })
    };
  }
}

/**
 * Validates a collection of entities against their schema
 * @param {Array} entities - Array of entities to validate
 * @param {string} schemaName - The name of the schema to validate against
 * @returns {Object} - Validation results with counts and error details
 */
function validateCollection(entities, schemaName) {
  if (!Array.isArray(entities)) {
    return {
      success: false,
      message: 'Input must be an array of entities',
      valid: 0,
      invalid: 0,
      errors: []
    };
  }

  let valid = 0;
  let invalid = 0;
  const errors = [];

  entities.forEach((entity, index) => {
    const result = validateEntity(entity, schemaName);
    if (result.success) {
      valid++;
    } else {
      invalid++;
      errors.push({
        index,
        id: entity.id || `[No ID at index ${index}]`,
        errors: result.errors
      });
    }
  });

  return {
    success: invalid === 0,
    message: invalid === 0 
      ? `All ${valid} entities are valid` 
      : `Found ${invalid} invalid entities out of ${entities.length}`,
    valid,
    invalid,
    errors
  };
}

/**
 * Validates relationships between entities
 * @param {Array} relationships - Array of relationship objects
 * @param {Object} entityMaps - Maps of entities by ID for each entity type
 * @returns {Object} - Validation results for relationships
 */
function validateRelationships(relationships, entityMaps) {
  if (!Array.isArray(relationships)) {
    return {
      success: false,
      message: 'Input must be an array of relationships',
      valid: 0,
      invalid: 0,
      errors: []
    };
  }

  let valid = 0;
  let invalid = 0;
  const errors = [];

  // First validate against relationship schema
  const schemaValidation = validateCollection(relationships, 'relationship');
  valid = schemaValidation.valid;
  invalid = schemaValidation.invalid;
  
  if (schemaValidation.errors.length > 0) {
    errors.push(...schemaValidation.errors);
  }

  // Then validate referential integrity
  relationships.forEach((rel, index) => {
    // Skip if already invalid from schema validation
    if (schemaValidation.errors.some(e => e.index === index)) {
      return;
    }

    const sourceMap = entityMaps[rel.source_type.toLowerCase()];
    const targetMap = entityMaps[rel.target_type.toLowerCase()];
    
    const sourceExists = sourceMap && sourceMap[rel.source_id];
    const targetExists = targetMap && targetMap[rel.target_id];
    
    if (!sourceExists || !targetExists) {
      invalid++;
      valid--;
      
      errors.push({
        index,
        id: rel.id,
        errors: [
          !sourceExists ? {
            path: '/source_id',
            message: `Source entity not found: ${rel.source_id} (${rel.source_type})`
          } : null,
          !targetExists ? {
            path: '/target_id',
            message: `Target entity not found: ${rel.target_id} (${rel.target_type})`
          } : null
        ].filter(Boolean)
      });
    }
  });

  return {
    success: invalid === 0,
    message: invalid === 0 
      ? `All ${valid} relationships are valid` 
      : `Found ${invalid} invalid relationships out of ${relationships.length}`,
    valid,
    invalid,
    errors
  };
}

/**
 * Validates a complete dataset with all entity types and relationships
 * @param {Object} dataset - Object containing arrays of entities by type
 * @returns {Object} - Complete validation results
 */
function validateDataset(dataset) {
  const results = {};
  const entityMaps = {};
  let totalValid = 0;
  let totalInvalid = 0;

  // Validate each entity type
  for (const [entityType, entities] of Object.entries(dataset)) {
    if (entityType === 'relationships') continue;
    
    if (Array.isArray(entities)) {
      results[entityType] = validateCollection(entities, entityType);
      totalValid += results[entityType].valid;
      totalInvalid += results[entityType].invalid;
      
      // Build entity maps for relationship validation
      if (!entityMaps[entityType]) {
        entityMaps[entityType] = {};
      }
      
      entities.forEach(entity => {
        if (entity.id) {
          entityMaps[entityType][entity.id] = entity;
        }
      });
    }
  }

  // Validate relationships if present
  if (dataset.relationships && Array.isArray(dataset.relationships)) {
    results.relationships = validateRelationships(dataset.relationships, entityMaps);
    totalValid += results.relationships.valid;
    totalInvalid += results.relationships.invalid;
  }

  return {
    success: totalInvalid === 0,
    message: totalInvalid === 0 
      ? `All ${totalValid} entities and relationships are valid` 
      : `Found ${totalInvalid} invalid entities or relationships out of ${totalValid + totalInvalid}`,
    results,
    totalValid,
    totalInvalid
  };
}

/**
 * Validates a data file against the schema
 * @param {string} filePath - Path to the JSON data file
 * @param {string} schemaName - Optional schema name if validating a single entity type
 * @returns {Object} - Validation results
 */
function validateFile(filePath, schemaName = null) {
  try {
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    
    if (schemaName) {
      // Validate against a specific schema
      if (Array.isArray(data)) {
        return validateCollection(data, schemaName);
      } else {
        return validateEntity(data, schemaName);
      }
    } else {
      // Validate as a complete dataset
      return validateDataset(data);
    }
  } catch (error) {
    return {
      success: false,
      message: `Error reading or parsing file: ${error.message}`,
      errors: [error]
    };
  }
}

/**
 * Prints validation results to the console
 * @param {Object} results - Validation results
 * @param {boolean} verbose - Whether to print detailed error information
 */
function printResults(results, verbose = false) {
  if (results.success) {
    console.log(chalk.green('✓ ' + results.message));
    return;
  }

  console.log(chalk.red('✗ ' + results.message));
  
  if (verbose && results.errors) {
    results.errors.forEach(error => {
      console.log(chalk.yellow(`\nEntity at index ${error.index}, ID: ${error.id}`));
      error.errors.forEach(err => {
        console.log(chalk.red(`  - ${err.path}: ${err.message}`));
      });
    });
  } else if (verbose && results.results) {
    for (const [entityType, typeResults] of Object.entries(results.results)) {
      if (!typeResults.success) {
        console.log(chalk.yellow(`\n${entityType}: ${typeResults.message}`));
        if (typeResults.errors && typeResults.errors.length > 0) {
          typeResults.errors.forEach(error => {
            console.log(chalk.yellow(`  Entity at index ${error.index}, ID: ${error.id}`));
            error.errors.forEach(err => {
              console.log(chalk.red(`    - ${err.path}: ${err.message}`));
            });
          });
        }
      } else {
        console.log(chalk.green(`\n${entityType}: ${typeResults.message}`));
      }
    }
  }
}

// Command line interface
if (require.main === module) {
  const args = process.argv.slice(2);
  
  if (args.length < 1) {
    console.log('Usage: node validate.js <data-file> [schema-name] [--verbose]');
    process.exit(1);
  }

  const filePath = args[0];
  const schemaName = args.length > 1 && !args[1].startsWith('--') ? args[1] : null;
  const verbose = args.includes('--verbose');

  const results = validateFile(filePath, schemaName);
  printResults(results, verbose);
  
  process.exit(results.success ? 0 : 1);
}

module.exports = {
  validateEntity,
  validateCollection,
  validateRelationships,
  validateDataset,
  validateFile,
  printResults
};

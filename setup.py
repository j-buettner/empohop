from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="planetary-health-kg",
    version="0.1.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A tool for extracting planetary health knowledge graphs from academic documents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/planetary-health-kg",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "extract-document=extract_document:main",
            "process-llm=llm_processor:main",
            "review-interface=main:main",
        ],
    },
)

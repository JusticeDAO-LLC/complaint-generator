from setuptools import find_packages, setup


setup(
    name="complaint-generator",
    version="0.1.0",
    description="Complaint generator workspace with CLI, MCP tools, and web surfaces.",
    packages=find_packages(
        include=[
            "adversarial_harness",
            "adversarial_harness.*",
            "applications",
            "applications.*",
            "backends",
            "backends.*",
            "complaint_analysis",
            "complaint_analysis.*",
            "complaint_generator",
            "complaint_generator.*",
            "complaint_phases",
            "complaint_phases.*",
            "integrations",
            "integrations.*",
            "lib",
            "lib.*",
            "mediator",
            "mediator.*",
        ]
    ),
    include_package_data=True,
    install_requires=[
        "ipfs_datasets_py[file_conversion,knowledge_graphs,scraping,vectors]>=0.2.0",
        "mcp>=1.2.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.30.0,<1.0.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
        "httpx>=0.25.2,<0.26.0",
        "python-multipart>=0.0.9",
        "PyJWT>=2.8.0,<3.0.0",
        "beautifulsoup4>=4.12.0,<5.0.0",
        "cryptography>=41.0.0",
        "python-docx>=1.1.2",
        "reportlab>=4.2.5",
        "typer>=0.12.0",
        "playwright>=1.53.0,<2.0.0",
    ],
    python_requires=">=3.12",
    entry_points={
        "console_scripts": [
            "complaint-generator=complaint_generator.entrypoints:main",
            "complaint-workspace=complaint_generator.cli:main",
            "complaint-generator-workspace=complaint_generator.cli:main",
            "complaint-mcp-server=complaint_generator.mcp_server:main",
            "complaint-generator-mcp=complaint_generator.mcp_server:main",
        ],
    },
)

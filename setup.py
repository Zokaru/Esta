from setuptools import setup, find_packages
import pathlib

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="esta",
    version="0.1.2",
    description="Minimal static site generator",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Zokaru/Esta/",
    author="Daniel Sánchez",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Environment :: Console",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Content Management System",
        "Topic :: Internet :: WWW/HTTP :: Site Management",
        "Topic :: Text Processing :: Markup :: HTML",
    ],
    keywords="static-site-generator, html, css-bundling, js-bundling, localisation, html-templating",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.7, <4",
    entry_points={
        "console_scripts": [
            "esta=esta.esta:main",
        ],
    },
)

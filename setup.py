from setuptools import setup, find_packages

import ogn_consumer


def long_description():
    with open('README.md', 'r') as f:
        return f.read()


tests_require = [
    'pytest',
    'flake8'
]


setup(
    name='OGN Consumer',
    version=ogn_consumer.__version__,
    description=ogn_consumer.__description__,
    long_description=long_description(),
    url='https://github.com/akolar/ogn-consumer',
    download_url='https://github.com/akolar/ogn-consumer',
    author=ogn_consumer.__author__,
    author_email=ogn_consumer.__author_email__,
    license=ogn_consumer.__license__,
    packages=find_packages(exclude=['docs', 'tests']),
    install_requires=[],
    tests_require=tests_require,
    classifiers=[],
)

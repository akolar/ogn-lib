from setuptools import setup, find_packages

import ogn_lib


def long_description():
    with open('README.md', 'r') as f:
        return f.read()


tests_require = [
    'pytest',
    'flake8'
]


setup(
    name='ogn-lib',
    version=ogn_lib.__version__,
    description=ogn_lib.__description__,
    long_description=long_description(),
    url='https://github.com/akolar/ogn-lib',
    download_url='https://github.com/akolar/ogn-lib',
    author=ogn_lib.__author__,
    author_email=ogn_lib.__author_email__,
    license=ogn_lib.__license__,
    packages=find_packages(exclude=['docs', 'tests']),
    install_requires=[],
    tests_require=tests_require,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Utilities'
    ],
)

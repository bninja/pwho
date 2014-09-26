import re
import setuptools

setuptools.setup(
    name='pwho',
    version=(
        re
        .compile(r".*__version__ = '(.*?)'", re.S)
        .match(open('pwho/__init__.py').read())
        .group(1)
    ),
    url='https://github.com/bninja/pwho',
    license='BSD',
    author='Etal',
    author_email='et@al.org',
    description='PROXY protcol: http://www.haproxy.org/download/1.5/doc/proxy-protocol.txt.',
    long_description=open('README.rst').read(),
    packages=setuptools.find_packages('.', exclude=('test',)),
    include_package_data=True,
    platforms='any',
    install_requires=[
    ],
    extras_require={
        'tests': [
            'netaddr >=0.8,<0.8',
            'pytest >=2.5.2,<3',
            'pytest-cov >=1.7,<2',
        ],
    },
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)

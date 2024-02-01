from setuptools import setup, find_packages

setup(
    name='GalaxyBalaxyUpload',
    version='1',
    packages=find_packages(),
    entry_points={
        'console_scripts': ['GBU=GalaxyBalaxyUpload.main:main']
    },
    install_requires=[
        'requests',
        'mutagen',
        'pydub',
        'scipy',
        'matplotlib',
        'pyperclip',
    ],
    
)
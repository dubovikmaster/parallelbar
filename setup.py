from setuptools import setup, find_packages

with open('README.md', encoding='utf-8') as f:
    long_description = f.read()


setup(
    name='parallelbar',
    version='0.2.13',
    packages=find_packages(),
    author='Dubovik Pavel',
    author_email='geometryk@gmail.com',
    description='Parallel processing with progress bars',
    long_description=long_description,
    long_description_content_type='text/markdown',
    keywords=[
        'progress bar',
        'tqdm',
        'parallelbar',
        'parallel tqdm',
        'parallel map',
        'parallel',
        'multiprocessing bar',
    ],
    url='https://github.com/dubovikmaster/parallelbar',
    license='MIT',
    install_requires=[
        'tqdm',
        'colorama',
        'pebble'
    ],
    platforms='any'
)

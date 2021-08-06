from setuptools import setup, find_packages


setup(
    name='parallelbar',
    version='0.1.13',
    packages=find_packages(),
    author='Dubovik Pavel',
    author_email='geometryk@gmail.com',
    description='Parallel processing with progress bars',
    keywords=[
        'progress bar',
        'tqdm',
        'parallelbar',
        'parallel tqdm',
        'parallel map',
        'parallel',
    ],
    url='https://github.com/dubovikmaster/parallelbar',
    license='MIT',
    install_requires=[
        'tqdm',
        'colorama',
    ],
    platforms='any'
)

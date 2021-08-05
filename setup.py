from setuptools import setup, find_packages


setup(
    name='parallelbar',
    version='0.1.7',
    packages=find_packages(),
    author='Dubovik Pavel',
    description='Parallel processing with progress bars',
    license='MIT',
    author_email='geometryk@gmail.com',
    install_requires=[
        'tqdm',
        'colorama',
    ],
    platforms='any'
)

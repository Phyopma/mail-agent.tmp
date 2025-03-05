from setuptools import setup, find_packages

setup(
    name='mail_agent',
    version='0.1',
    packages=['mail_agent', 'email_fetcher', 'email_preprocessor',
              'email_tagger', 'calendar_agent', 'spam_detector'],
    install_requires=[
        'google-auth>=2.3.0',
        'google-api-python-client>=2.84.0',
        'google-auth-oauthlib>=0.4.6',  # Added missing dependency
        'python-dotenv>=0.19.0',
        'argparse>=1.4.0',
        'aiohttp>=3.8.0',  # Fixed missing comma
        'pydantic>=2.0.0',
        'pytz>=2023.3'
    ],
    entry_points={
        'console_scripts': [
            'mail-agent=mail_agent.main:main'
        ],
    },
    package_dir={'': '.'},
    python_requires='>=3.8',
)

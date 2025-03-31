from setuptools import setup, find_packages

setup(
    name='mail_agent',
    version='0.1',
    packages=['mail_agent', 'email_fetcher', 'email_preprocessor',
              'email_tagger', 'calendar_agent', 'spam_detector'],
    install_requires=[
        'pydantic>=2.0.0',
        'asyncio>=3.4.3',
        'google-auth-oauthlib>=1.0.0',
        'google-auth-httplib2>=0.1.0',
        'google-api-python-client>=2.0.0',
        'python-dateutil>=2.8.2',
        'openai',
        'dotenv',
        'bs4'
    ],
    entry_points={
        'console_scripts': [
            'mail_agent=mail_agent.main:main'
        ],
    },
    package_dir={'': '.'},
    python_requires='>=3.8',
)

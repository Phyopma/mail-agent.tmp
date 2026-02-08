from setuptools import setup, find_packages

setup(
    name='mail_agent',
    version='0.1',
    packages=['mail_agent', 'email_fetcher', 'email_preprocessor',
              'email_tagger', 'calendar_agent', 'spam_detector'],
    install_requires=[
        'google-auth-oauthlib>=1.0.0',
        'google-auth-httplib2>=0.1.0',
        'google-api-python-client>=2.0.0',
        'langchain==1.2.7',
        'langchain-core==1.2.8',
        'langchain-google-genai==4.2.0',
        'langgraph==1.0.7',
        'pydantic>=2.0.0',
        'python-dateutil>=2.8.2',
        'python-dotenv>=1.0.0',
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

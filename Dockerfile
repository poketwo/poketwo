FROM gorialis/discord.py:build1-3.8.1-buster

# Install app dependencies.
RUN pip install pipenv
RUN pipenv install

CMD ["python", "main.py"]
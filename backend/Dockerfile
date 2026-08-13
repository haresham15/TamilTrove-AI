FROM python:3.10

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Pre-download the embedding model so it's cached in the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . /code

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]

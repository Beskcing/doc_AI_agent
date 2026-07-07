FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e ".[all]"

EXPOSE 8000

CMD ["python", "-m", "scripts.run_server", "--port", "8000"]

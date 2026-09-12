FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/app.py ./app.py
COPY frontend/components.py ./components.py
COPY frontend/demo.py ./demo.py
COPY frontend/result_summary.py ./result_summary.py
COPY frontend/report.py ./report.py
COPY frontend/styles.py ./styles.py
COPY frontend/assets ./assets

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]

FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY scripts ./scripts
COPY data ./data
COPY pickle ./pickle
COPY run.sh ./

RUN chmod +x run.sh

CMD ["./run.sh", "./data", "./pickle/model.pkl", "./output/predictions.csv"]

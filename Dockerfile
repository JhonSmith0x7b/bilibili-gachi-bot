FROM python:3.12-bullseye

WORKDIR /app

COPY requirements.txt .
# RUN pip install -r requirements.txt
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple
COPY ./app /app/
RUN chmod -R 777 /root
RUN chmod -R 777 /app

EXPOSE 7860
CMD python -m http.server 7860 & python main.py
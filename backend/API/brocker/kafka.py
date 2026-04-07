import os
import socket
from confluent_kafka import Producer
from dotenv import load_dotenv

class KafkaProducer:

    def __init__(self):
        load_dotenv()

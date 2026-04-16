import json
import threading
import tomllib
import os
from confluent_kafka import Consumer, KafkaError

def load_config():
    comfig_path = os.path.join(os.path.dirname(__file__), 'brocker_config.toml')
    with open(comfig_path, 'rb') as f:
        return tomllib.load(f)

class KafkaConsumer:

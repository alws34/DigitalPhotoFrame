from PhotoFrame import PhotoFrame
from flask import Flask
from flask_cors import CORS
from flask_restful import Resource, Api

app = Flask(__name__)
CORS(app)
api = Api(app)

if __name__ == "__main__":
    frame = PhotoFrame()
    frame.main()

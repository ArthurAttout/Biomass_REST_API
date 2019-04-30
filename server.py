from flask import Flask
from keras.preprocessing.image import ImageDataGenerator
import numpy as np
from PIL import Image
from io import BytesIO
import json
import base64
import os, sys
from keras.models import load_model
from flask import request
import urllib.request

app = Flask(__name__)
array_class = ["african_herbs","hay","marjorem","moss_green","moss_grey","rabbit_food","rosemary","sugar","tobacco"]
model = load_model("/data/tera_1/partage/rest_api/model.hdf5")
model._make_predict_function()
img_width, img_height = 250, 250


@app.route('/identify', methods = ['POST'])
def postJsonHandler():
	content = request.get_json()
	url_host = content['url']
	
	print(url_host)
	
	with urllib.request.urlopen(url_host) as response:

		im = Image.open(BytesIO(response.read()))
		im = im.resize((img_width, img_height))

		arr = np.array(im)
		arrPred = np.asarray([i / 255 for i in arr.reshape(187500)])
		pred = model.predict(arrPred.reshape(1,img_width,img_height,3))
		float_list = [float(i) for i in list(pred[0])]
		response = {
			"predictions":float_list,
			"likely_class":float_list.index(max(float_list))
		}
		return json.dumps(response)
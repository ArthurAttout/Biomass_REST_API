# REST API

from flask import Flask
from keras.preprocessing.image import ImageDataGenerator
import numpy as np
from PIL import Image
from io import BytesIO
import mysql.connector
import json
import base64
import os, sys
from keras.models import load_model
from flask import request
import urllib.request

app = Flask(__name__)

@app.route('/identify', methods = ['POST'])
def identifyHandler():
	content = request.get_json()
	url_host = content['url']
	
	print(url_host)
	
	#Forward request to ML component
	req = urllib.request.Request("http://192.168.1.85:5001")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	jsondata = json.dumps(content)
	jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
	req.add_header('Content-Length', len(jsondataasbytes))
	response = urllib.request.urlopen(req, jsondataasbytes)
	data = response.read()
	encoding = response.info().get_content_charset('utf-8')
	JSON_object = json.loads(data.decode(encoding))
	
	if(max(JSON_object['predictions']) > 0.87):
		# If certitude > 87%, return object as-is
		return JSON_object
	else:
		# Else, ask for geolocation
		response = {
			"error":"BAD_CERTITUDE"
		}
		return json.dumps(response)
	
@app.route('/geolocation', methods = ['POST'])
def geolocationHandler():
	content = request.get_json()
	
	url_host = content['url']
	latitude = content['latitude']
	longitude = content['longitude']
	
	print("LatLng : {} - {}".format(latitude,longitude))
	
	#Get list of excluded classes
	mydb = mysql.connector.connect(
	  host="192.168.1.67",
	  user="python",
	  passwd="python",
	  database="biomass_database"
	)
	cursor = mydb.cursor()
	query = '''	
		select class_ML from biomass
		where class_ML not in(
		select class_ML from biomass 
		where (Abs(biomass.latitude_up) > {0} AND Abs(biomass.longitude_up) > {1})
		AND   (Abs(biomass.latitude_down) < {0} AND Abs(biomass.longitude_down) < {1})
		OR    (biomass.latitude_down is null))
	'''
	cursor.execute(query.format(latitude,longitude))
	result = cursor.fetchall()
	classes_excluded = [x[0] for x in result]
	
	#Forward request to ML component with classes
	
	req = urllib.request.Request("http://192.168.1.85:5001")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	payload = {
		"url":url_host,
		"classes_to_exclude":classes_excluded
	}
	
	jsondata = json.dumps(payload)
	jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
	req.add_header('Content-Length', len(jsondataasbytes))
	response = urllib.request.urlopen(req, jsondataasbytes)
	data = response.read()
	encoding = response.info().get_content_charset('utf-8')
	JSON_object = json.loads(data.decode(encoding))
	
	if(max(JSON_object['predictions']) > 0.87):
		# If certitude > 87%, return object as-is
		return JSON_object
	
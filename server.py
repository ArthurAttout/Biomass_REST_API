#!/usr/bin/env python

# REST API

from flask import Flask
import numpy as np
from PIL import Image
from io import BytesIO
import mysql.connector
import json
import base64
import os, sys
from flask import request
import urllib2
from werkzeug.serving import run_simple

app = Flask(__name__)
app.debug = True

mydb = mysql.connector.connect(
	host="192.168.1.67",
	user="python",
	passwd="python",
	database="biomass_database"
)

def get_biomass_name_from_class(class_number):
	cursor = mydb.cursor()
	query = '''	
		select name from biomass
		where class_ML = {}
	'''
	cursor.execute(query.format(class_number))
	result = cursor.fetchall()
	return [x[0] for x in result][0]

@app.route('/identify', methods = ['POST'])
def identifyHandler():
	content = request.get_json()
	url_host = content['url']
	
	print(url_host)
	
	#Forward request to ML component
	req = urllib2.Request("http://192.168.1.85:5001/identify")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	jsondata = json.dumps(content)
	jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
	req.add_header('Content-Length', len(jsondataasbytes))
	response = urllib2.urlopen(req, jsondataasbytes)
	
	JSON_object = json.load(response)
	
	if(max(JSON_object['predictions']) > 0.87):
		# If certitude > 87%, return object as-is
		print("Getting biomass name for {}".format(JSON_object['likely_class']))
		biomass_name = get_biomass_name_from_class(JSON_object['likely_class'])
		response = {
			"result" : "OK",
			"biomass_name": biomass_name,
			"certitude" : max(JSON_object['predictions'])
		}
		return json.dumps(response)
	else:
		# Else, ask for geolocation
		response = {
			"result":"BAD_CERTITUDE"
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
	
	req = urllib2.Request("http://192.168.1.85:5001/identifyWithMask")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	payload = {
		"url":url_host,
		"classes_to_exclude":classes_excluded
	}
	
	jsondata = json.dumps(payload)
	jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
	req.add_header('Content-Length', len(jsondataasbytes))
	response = urllib2.urlopen(req, jsondataasbytes)
	JSON_object = json.load(response)
	
	if(max(JSON_object['predictions']) > 0.87):
		# If certitude > 87%, return object as-is
		biomass_name = get_biomass_name_from_class(JSON_object['likely_class'])
		response = {
			"result" : "OK",
			"biomass_name": biomass_name,
			"certitude" : max(JSON_object['predictions'])
		}
		return json.dumps(JSON_object)
	else:
		# Still don't know.
		response = {
			"result":"BAD_CERTITUDE"
		}
		return json.dumps(response)
	
if __name__ == '__main__':
    app.run(host = '0.0.0.0',port=5000)

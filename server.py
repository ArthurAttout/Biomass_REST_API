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
import asyncio
from flask import request
import urllib.request
from werkzeug.serving import run_simple
from websocket import create_connection
import datetime


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
	
	
def get_valorizations_for_biomass(class_number):
	cursor = mydb.cursor()
	query = '''
		SELECT FORMAT(cellulose,0),FORMAT(hemicellulose,0),FORMAT(lignine,0),
		(select shortname from valorisation where id = FK_Valorisation) as valorization
		FROM biomass_database.matrix_valorisation 
		where FK_Biomass = {}
		order by cellulose, hemicellulose, lignine
	'''
	cursor.execute(query.format(class_number))
	result = cursor.fetchall()
	return result
	
def add_to_history(biomass_id, img_path, certitude):
	cursor = mydb.cursor()
	query_insert_image = '''
		INSERT INTO report_image (path) 
		VALUES ('{}');
	'''
	cursor.execute(query_insert_image.format(img_path))
	image_id = cursor.lastrowid
	mydb.commit()
	
	query_insert_history = '''
		INSERT INTO history (date, FK_Biomass, FK_Image, certitude) 
		VALUES ('{0}', '{1}', '{2}', '{3}');
	'''
	today = datetime.datetime.now()
	cursor.execute(query_insert_history.format(today, biomass_id, image_id, certitude))
	mydb.commit()
	return cursor.lastrowid

@app.route('/identify', methods = ['POST'])
def identifyHandler():
	content = request.get_json()
	url_host = content['url']
	
	print(url_host)
	
	#Forward request to ML component
	
	req = urllib.request.Request("http://192.168.1.85:5001/identify")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	jsondata = json.dumps(content)
	jsondataasbytes = jsondata.encode('utf-8')
	req.add_header('Content-Length', len(jsondataasbytes))
	
	print("DECODE")
	response = urllib.request.urlopen(req, jsondataasbytes).read().decode("utf-8")
	JSON_object = json.loads(response)
	
	
	if(max(JSON_object['predictions']) > 0.95):
		# If certitude > 95%, return object as-is
		biomass_id = JSON_object['likely_class']
		print("Getting biomass name for {}".format(biomass_id))
		biomass_name = get_biomass_name_from_class(biomass_id)
		certitude =  max(JSON_object['predictions'])
		response_client = {
			"result" : "OK",
			"biomass_name": biomass_name,
			"certitude" : certitude,
			"valorizations" : get_valorizations_for_biomass(JSON_object['likely_class'])
		}
		
		new_id = add_to_history(biomass_id,url_host,certitude)
		payload_dashboard = {
			"type":"NEW_HISTORY",
			"element":{
				"id":new_id,
				"date": str(datetime.datetime.now()),
				"name": biomass_name,
				"certitude": certitude
			}
		}
		ws = create_connection("ws://192.168.1.85:8080/")
		ws.send(json.dumps(payload_dashboard))
		ws.close()
		return json.dumps(response_client)
		
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
	crop = content['crop']
	
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
	
	req = urllib.request.Request("http://192.168.1.85:5001/identifyWithMask")
	req.add_header('Content-Type', 'application/json; charset=utf-8')
	payload = {
		"url":url_host,
		"classes_to_exclude":classes_excluded,
		"crop":crop,
	}
	print("Sending payload to ML {}".format(payload))
	jsondata = json.dumps(payload)
	jsondataasbytes = jsondata.encode('utf-8')   # needs to be bytes
	req.add_header('Content-Length', len(jsondataasbytes))
	response = urllib.request.urlopen(req, jsondataasbytes).read().decode('utf-8')
	JSON_object = json.loads(response)
	
	if(max(JSON_object['predictions']) > 0.95):
		# If certitude > 95%, return object as-is
		biomass_name = get_biomass_name_from_class(JSON_object['likely_class'])
		response = {
			"result" : "OK",
			"biomass_name": biomass_name,
			"certitude" : max(JSON_object['predictions']),
			"valorizations" : get_valorizations_for_biomass(JSON_object['likely_class'])
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

import cv2
from flask import Flask, render_template, Response, request
from time import time, sleep

try:
    from motors import *
except:
    class MotorThread:
        def __init__(self):            
            self.dx, self.dy = 0, 0
        def start(self):
            print("Wrooom wroom!!!! (no motors found) ")
        def set(self, m1, m2, m3):
            pass

from camera import CameraMaster

motors = MotorThread()
motors.start()

cameras = CameraMaster(target=motors)
print('grabber count', cameras.slaveCount)    

app = Flask(__name__)

@app.route('/video')
def video():
    def generator():
        while True:
            last_frame = cameras.getGroupPhoto()
                
            ret, jpeg = cv2.imencode('.jpg', last_frame, (cv2.IMWRITE_JPEG_QUALITY, 80))
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tostring() + b'\r\n\r\n'
            sleep(0.05)
    return Response(generator(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/')
def index():
    return render_template('sliders.html')

@app.route('/test')
def testIntroduce():
    return render_template('generateFormsExampleTemplate.html', camera_list = cameras.introduceSlaves() )

# static files for js and css
@app.route('/nouislider.css')
def nouisliderCSS():
    return render_template('nouislider.css')
@app.route('/nouislider.js')
def nouisliderJS():
    return render_template('nouislider.js')

# @app.route('/camera/config', methods=['get', 'post'])
# def config():
#     global grab1 # will nuke later

#     blH = int(request.form.get('blH')) #int cant be none
#     blS = int(request.form.get('blS'))
#     blV = int(request.form.get('blV'))
#     bhH = int(request.form.get('bhH'))
#     bhS = int(request.form.get('bhS'))
#     bhV = int(request.form.get('bhV'))
#     print ("lower range is now: " , grab1.BALL_LOWER , (blH, blS, blV))
#     grab1.BALL_LOWER = (blH, blS, blV)
#     print("Higher range is now: " ,grab1.BALL_UPPER, (bhH, bhS, bhV))
#     grab1.BALL_UPPER = (bhH, bhS, bhV)
#     return "OK" 

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, use_reloader=False, threaded=True)
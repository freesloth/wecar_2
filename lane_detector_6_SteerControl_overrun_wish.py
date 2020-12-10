#!/usr/bin/env python

import rospy, cv2
import numpy as np
import os, rospkg, json, time ,math
from threading import Thread
from sensor_msgs.msg import CompressedImage, LaserScan,PointCloud
from geometry_msgs.msg import Point32
from cv_bridge import CvBridgeError

from utilsco import purePursuit

class IMGParser:
    def __init__(self, currentPath):
        self.img = None
        #region fixed code cam set
        self.cameraFeed = True
        #self.videoPath = currentPath + "/scripts/drive_video/sample_drive.mp4"
        #self.videoPath = currentPath + "/scripts/drive_video/drive.avi"
        #self.videoPath = currentPath + "/scripts/drive_video/drive_dark.avi"
        #self.videoPath = currentPath + "/scripts/drive_video/drive_high_angle.avi"
        #self.videoPath = currentPath + "/scripts/drive_video/2020-09-29-01-57-22.bag"
        #self.videoPath = currentPath + "/scripts/drive_video/2020-10-14-04-42-31.bag"
        self.videoPath = currentPath + "/scripts/drive_video/2020-10-15-05-57-52.bag" #10 70 0 100, (120, 135, 130)
        self.cameraNo = 1
        self.cameraWidth = 640
        self.cameraHeight = 360
        self.frameWidth = 640
        self.frameHeight = 360
        #endregion
        self.set_cam()
        self.saving_ret = False
        self.saving_img = None
        self.keep_reading = True

        #region Trackbar side
        self.trackbar_change_flag = False
        self.speed_change_flag = False
        self.trackbar_name = "Control Panel"
        #endregion

        #region Warp init
        self.warp_arrays = np.float32([[0,0], [0,0], [0,0], [0,0]])
        #endregion

        #region sliding windows data
        self.left_a, self.left_b, self.left_c = [], [], []
        self.right_a, self.right_b, self.right_c = [], [], []
        #endregion

        #region lane curved data
        self.noOfArrayValues = 10 
        self.arrayCounter = 0
        self.arrayCurve = np.zeros([self.noOfArrayValues])
        #endregion

        #region lane curve data
        self.ym_per_pix = float(0.6) / float(self.frameHeight)  # front meter / Hight pixels
        self.xm_per_pix = float(0.8) / float(self.frameWidth)  # lane side meter / Width pixel
        #endregion

    def set_cam(self):
        if self.cameraFeed:
            self.cam = cv2.VideoCapture(self.cameraNo)
            self.cam.set(3, self.cameraWidth)
            self.cam.set(4, self.cameraHeight)
            self.cam.set(28, 0)
        else:
            self.cam = cv2.VideoCapture(self.videoPath)
        
    def get_image(self):
        ret, image = self.cam.read()
        
        if not ret:
            self.set_cam()
        else:
            if not (self.frameWidth == self.cameraWidth and self.frameHeight == self.cameraHeight):
                image = cv2.resize(image, (self.frameWidth, self.frameHeight), interpolation = cv2.INTER_AREA)

        return ret, image
    
    def get_image_continue(self):
        while(self.keep_reading):
            self.saving_ret, self.saving_img = self.get_image()
            time.sleep(0.03)
        
    def image_process(self, inpImage):
        # Apply HLS color filtering to filter out white lane lines
        imgMat = inpImage
        #imgMat = cv2.UMat(inpImage)
        hlsMat = cv2.cvtColor(imgMat, cv2.COLOR_BGR2HLS)
        #lower_white = np.array([137, 93, 139]) #136 164 101
        lower_white = np.array([135, 141, 136]) #136 164 101
        upper_white = np.array([255, 255, 255])
        mask = cv2.inRange(imgMat, lower_white, upper_white)
        imgMat = cv2.bitwise_and(imgMat, hlsMat, mask = mask)
        
        # Convert image to grayscale, apply threshold, blur & extract edges
        imgMat = cv2.cvtColor(imgMat, cv2.COLOR_BGR2GRAY)
        ret, imgMat = cv2.threshold(imgMat, 78, 255, cv2.THRESH_BINARY)
        imgMat = cv2.GaussianBlur(imgMat,(3, 3), 0)
        imgMat = cv2.Canny(imgMat, 40, 60)
        
        return imgMat

    def drawPoints(self, img, src):
        #drawing circles on frame
        img_size = np.float32([(self.frameWidth, self.frameHeight)])
        #src = np.float32([(0.43, 0.65), (0.58, 0.65), (0.1, 1), (1, 1)])
        src = src * img_size
        for x in range( 0,4): 
            cv2.circle(img,(int(src[x][0]),int(src[x][1])),5,(0,255,0),cv2.FILLED)
        return img

    #region Image Warp, insult mark point. (DRAW POINT->Perspective->Perspective->Perspective)
    def perspectiveWarp_init(self, srcs):
        # Get image size
        img_w = self.frameWidth
        img_h = self.frameHeight

        img_size = (img_w, img_h)

        srcs *= img_size
        for x in range(0, 4):
            self.warp_arrays[x][0] = int(srcs[x][0])
            self.warp_arrays[x][1] = int(srcs[x][1])

        # Window to be shown
        dst = np.float32([[0, 0], [img_w, 0], [0, img_h], [img_w, img_h]])

        # Matrix to warp the image for birdseye window
        self.matrix = cv2.getPerspectiveTransform(self.warp_arrays, dst)
        # Inverse matrix to unwarp the image for final window
        self.minv = cv2.getPerspectiveTransform(dst, self.warp_arrays)

    def perspectiveWarp(self, inpImage, srcs):
        return cv2.warpPerspective(inpImage, self.matrix, (self.frameWidth, self.frameHeight))
    #endregion

    #region Sliding windows shape[0] = H
    def get_hist(self, img):
        hist = np.sum(img[self.frameHeight//2:,:], axis=0)
        return hist

    def sliding_window(self, img, draw_windows=True):
        # Find the start of left and right lane lines using histogram info
        out_img = np.dstack((img, img, img)) * 255
        #midpoint = np.int(histogram.shape[0] / 2)
        midpoint = np.int(self.frameWidth / 2)
        histogram = self.get_hist(img)
        leftx_base = np.argmax(histogram[:midpoint])
        rightx_base = np.argmax(histogram[midpoint:]) + midpoint

        # A total of 9 windows will be used
        nwindows = 8
        #window_height = np.int(binary_warped.shape[0] / nwindows)
        window_height = np.int(self.frameHeight / nwindows)
        nonzero = img.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])
        leftx_current = leftx_base
        rightx_current = rightx_base
        margin = 40
        minpix = 30
        left_lane_inds = []
        right_lane_inds = []

        #### START - Loop to iterate through windows and search for lane lines #####
        for window in range(nwindows):
            #win_y_low = binary_warped.shape[0] - (window + 1) * window_height
            win_y_low = self.frameHeight - (window + 1) * window_height
            #win_y_high = binary_warped.shape[0] - window * window_height
            win_y_high = self.frameHeight - window * window_height
            win_xleft_low = leftx_current - margin
            win_xleft_high = leftx_current + margin
            win_xright_low = rightx_current - margin
            win_xright_high = rightx_current + margin
            cv2.rectangle(out_img, (win_xleft_low, win_y_low), (win_xleft_high, win_y_high),
            (0,255,0), 2)
            cv2.rectangle(out_img, (win_xright_low,win_y_low), (win_xright_high,win_y_high),
            (0,255,0), 2)
            good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
            (nonzerox >= win_xleft_low) &  (nonzerox < win_xleft_high)).nonzero()[0]
            good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) &
            (nonzerox >= win_xright_low) &  (nonzerox < win_xright_high)).nonzero()[0]
            left_lane_inds.append(good_left_inds)
            right_lane_inds.append(good_right_inds)
            if len(good_left_inds) > minpix:
                leftx_current = np.int(np.mean(nonzerox[good_left_inds]))
            if len(good_right_inds) > minpix:
                rightx_current = np.int(np.mean(nonzerox[good_right_inds]))
        #### END - Loop to iterate through windows and search for lane lines #######

        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)

        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]

        # Apply 2nd degree polynomial fit to fit curves
        left_fit = np.polyfit(lefty, leftx, 2)
        right_fit = np.polyfit(righty, rightx, 2)

        #ploty = np.linspace(0, binary_warped.shape[0]-1, binary_warped.shape[0])
        ploty = np.linspace(0, self.frameHeight-1, self.frameHeight)
        left_fitx = left_fit[0] * ploty**2 + left_fit[1] * ploty + left_fit[2]
        right_fitx = right_fit[0] * ploty**2 + right_fit[1] * ploty + right_fit[2]

        ltx = np.trunc(left_fitx)
        rtx = np.trunc(right_fitx)
        #plt.plot(right_fitx)
        #plt.show()

        out_img[nonzeroy[left_lane_inds], nonzerox[left_lane_inds]] = [255, 0, 0]
        out_img[nonzeroy[right_lane_inds], nonzerox[right_lane_inds]] = [0, 0, 255]

        # plt.imshow(out_img)
        #plt.plot(left_fitx,  ploty, color = 'yellow')
        #plt.plot(right_fitx, ploty, color = 'yellow')
        #plt.xlim(0, img_w)
        #plt.ylim(img_h, 0)

        return out_img, ploty, left_fit, right_fit, ltx, rtx

    def general_search(self, binary_warped, left_fit, right_fit):
        nonzero = binary_warped.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])
        margin = 50
        
        left_lane_inds = ((nonzerox > (left_fit[0]*(nonzeroy**2) + left_fit[1]*nonzeroy + left_fit[2] - margin)) 
        & (nonzerox < (left_fit[0]*(nonzeroy**2) + left_fit[1]*nonzeroy + left_fit[2] + margin)))

        right_lane_inds = ((nonzerox > (right_fit[0]*(nonzeroy**2) + right_fit[1]*nonzeroy + right_fit[2] - margin)) 
        & (nonzerox < (right_fit[0]*(nonzeroy**2) + right_fit[1]*nonzeroy + right_fit[2] + margin)))

        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds]
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]
        left_fit = np.polyfit(lefty, leftx, 2)
        right_fit = np.polyfit(righty, rightx, 2)
        #ploty = np.linspace(0, binary_warped.shape[0]-1, binary_warped.shape[0])
        ploty = np.linspace(0, self.frameWidth-1, self.frameWidth)
        left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
        right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]

        ret = {}
        ret['leftx'] = leftx
        ret['rightx'] = rightx
        ret['left_fitx'] = left_fitx
        ret['right_fitx'] = right_fitx
        ret['ploty'] = ploty

        return ret

    def measure_lane_curvature(self, ploty, leftx, rightx):
        leftx = leftx[::-1]  # Reverse to match top-to-bottom in y
        rightx = rightx[::-1]  # Reverse to match top-to-bottom in y

        # Choose the maximum y-value, corresponding to the bottom of the image
        y_eval = np.max(ploty)

        # Fit new polynomials to x, y in world space
        left_fit_cr = np.polyfit(ploty*self.ym_per_pix, leftx*self.xm_per_pix, 2)
        right_fit_cr = np.polyfit(ploty*self.ym_per_pix, rightx*self.xm_per_pix, 2)

        # Calculate the new radii of curvature
        left_curverad  = ((1 + (2*left_fit_cr[0]*y_eval*self.ym_per_pix + left_fit_cr[1])**2)**1.5) / np.absolute(2*left_fit_cr[0])
        right_curverad = ((1 + (2*right_fit_cr[0]*y_eval*self.ym_per_pix + right_fit_cr[1])**2)**1.5) / np.absolute(2*right_fit_cr[0])
        # Now our radius of curvature is in meters
        # print(left_curverad, 'm', right_curverad, 'm')

        # Decide if it is a left or a right curve
        if leftx[0] - leftx[-1] > 60:
            curve_direction = 'Left Curve'
        elif leftx[-1] - leftx[0] > 60:
            curve_direction = 'Right Curve'
        else:
            curve_direction = 'Straight'

        return (left_curverad + right_curverad) / 2.0, curve_direction
    
    def offCenter(self, draw_info):
        #leftx = draw_info['leftx']
        #rightx = draw_info['rightx']
        left_fitx = draw_info['left_fitx']
        right_fitx = draw_info['right_fitx']
        ploty = draw_info['ploty']

        mean_x = np.mean((left_fitx, right_fitx), axis=0)
        meanPts = np.array([np.flipud(np.transpose(np.vstack([mean_x, ploty])))])

        # Calculating deviation in meters
        mpts = meanPts[-1][-1][-2].astype(int)
        #pixelDeviation = inpFrame.shape[1] / 2 - abs(mpts)
        pixelDeviation = self.frameWidth / 2 - abs(mpts)
        deviation = pixelDeviation * self.xm_per_pix
        direction = "left" if deviation < 0 else "right"

        return deviation, direction

    #endregion

    #region Curved angle calculate
    def get_curve(self, img, leftx, rightx):
        ploty = np.linspace(0, img.shape[0] - 1, img.shape[0])
        y_eval = np.max(ploty)
        ym_per_pix = float(1) / float(img.shape[0])  # meters per pixel in y dimension
        xm_per_pix = float(0.1) / float(img.shape[0])  # meters per pixel in x dimension

        # Fit new polynomials to x,y in world space
        left_fit_cr = np.polyfit(ploty * ym_per_pix, leftx * xm_per_pix, 2)
        right_fit_cr = np.polyfit(ploty * ym_per_pix, rightx * xm_per_pix, 2)
        # Calculate the new radii of curvature
        left_curverad = ((1 + (2 * left_fit_cr[0] * y_eval * ym_per_pix + left_fit_cr[1]) ** 2) ** 1.5) / np.absolute(
            2 * left_fit_cr[0])
        right_curverad = ((1 + (2 * right_fit_cr[0] * y_eval * ym_per_pix + right_fit_cr[1]) ** 2) ** 1.5) / np.absolute(
            2 * right_fit_cr[0])

        car_pos = float(img.shape[1]) / float(2)
        l_fit_x_int = left_fit_cr[0] * img.shape[0] ** 2 + left_fit_cr[1] * img.shape[0] + left_fit_cr[2]
        r_fit_x_int = right_fit_cr[0] * img.shape[0] ** 2 + right_fit_cr[1] * img.shape[0] + right_fit_cr[2]
        lane_center_position = float(r_fit_x_int + l_fit_x_int) / 2
        center = (car_pos - lane_center_position) * float(xm_per_pix) / 10
        # Now our radius of curvature is in meters
        #print(l_fit_x_int, r_fit_x_int, center)
        return (l_fit_x_int, r_fit_x_int, center)
    #endregion

    #region CODE BLOCK REGION -> IOELECTRON TRACKBAR CONTROL
    def trackbar_ctrl(self, x):
        self.trackbar_change_flag = True

    def speed_change(self, x):
        self.speed_change_flag = True
        
    def initializeTrackbars(self, intialTracbarVals, intialCarRef):
        #intializing trackbars for region of intrest
        cv2.namedWindow(self.trackbar_name, cv2.WINDOW_NORMAL)
        cv2.createTrackbar("Top-X", self.trackbar_name, intialTracbarVals[0], 100, self.trackbar_ctrl)
        cv2.createTrackbar("Top-Y", self.trackbar_name, intialTracbarVals[1], 100, self.trackbar_ctrl)
        cv2.createTrackbar("Bottom-X", self.trackbar_name, intialTracbarVals[2], 100, self.trackbar_ctrl)
        cv2.createTrackbar("Bottom-Y", self.trackbar_name, intialTracbarVals[3], 100, self.trackbar_ctrl)
        cv2.createTrackbar("Speed", self.trackbar_name, intialCarRef, 500, self.speed_change)
        cv2.resizeWindow(self.trackbar_name, 700, 600)
        
    def valTrackbars(self):
        #getting the values of ROI, python2 version float error must float
        widthTop = float(cv2.getTrackbarPos("Top-X", self.trackbar_name))
        heightTop = float(cv2.getTrackbarPos("Top-Y", self.trackbar_name))
        widthBottom = float(cv2.getTrackbarPos("Bottom-X", self.trackbar_name))
        heightBottom = float(cv2.getTrackbarPos("Bottom-Y", self.trackbar_name))

        src = np.float32([(widthTop/100, heightTop/100), (1-(widthTop/100), (heightTop/100)),
                        (widthBottom/100, heightBottom/100), (1-(widthBottom/100), heightBottom/100)])
        #src = np.float32([widthTop, heightTop/100, widthBottom/100, heightBottom, speed_lv])
        #src = np.float32([(0.43, 0.65), (0.58, 0.65), (0.1, 1), (1, 1)])
        return src
    def valTrackbar_speed(self):
        return cv2.getTrackbarPos("Speed", self.trackbar_name)
    #endregion

class LASERParser:
    def __init__(self):

        self.scan_sub = rospy.Subscriber("/scan", LaserScan, self.callback)
        self.pcd_pub = rospy.Publisher('laser2pcd',PointCloud, queue_size=1)
        self.scan_dis = None
        self._is_lc=False
        self.back_detect =False
        self.left_detect =False
        
        
    def callback(self, msg):

        ranges = msg.ranges
        self.scan_dis = np.mean(ranges[350:360])

        back_range_max = 1000
        for i in range(0, 15):
            if str(ranges[i]) == 'inf' or str(ranges[i]) == 'None': continue
            if back_range_max > ranges[i]: back_range_max = ranges[i]
        for i in range(345, 360):
            if str(ranges[i]) == 'inf' or str(ranges[i]) == 'None': continue
            if back_range_max < ranges[i]: back_range_max = ranges[i]
        #print("back_range",str(back_range_max))
        if back_range_max < 0.6: self.back_detect = True
        

        

        left_range_max = 1000
        for i in range(40, 165):
            if str(ranges[i]) == 'inf' or str(ranges[i]) == 'None': continue
            if left_range_max > ranges[i]: left_range_max = ranges[i]
        #print("left_range",str(left_range_max))
        if left_range_max < 0.9: self.left_detect = True
        else: self.left_detect = False

        

       
        

        #  pcd=PointCloud()
        #  pcd.header.frame_id=msg.header.frame_id
        # angle=0
        # for r in ranges :
        #     tmp_point=Point32()
        #     tmp_point.x=r*math.cos(angle)
        #     tmp_point.y=r*math.sin(angle)
            
        #     angle=angle+(1.0/180*math.pi)
        #     if r<12  :
        #         pcd.points.append(tmp_point)
        #         # print(angle,tmp_point.x,tmp_point.y)

        # count=0
        # for point in pcd.points :
        #     if -1.0 < point.x < 1.0 and 0.1 < point.y < 1.0 :
        #         count+=1
        # #print(count)
        # if count > 50 :
        #     self._is_lc=False 
        # else :
        #     self._is_lc=True
            

        #self.pcd_pub.publish(pcd)

if __name__ == '__main__':
    rp= rospkg.RosPack()
    currentPath = rp.get_path("line")
    rospy.init_node('lane_detector',  anonymous=True)

    intialTracbarVals = [18,78,9,92]
    #intialTracbarVals = [28,87,0,100]
    #intialTracbarVals = [10,70,0,100]
    intialCarRef = 226

    ctrl_lat = purePursuit(lfd=0.8)
    image_parser = IMGParser(currentPath)
    image_parser.initializeTrackbars(intialTracbarVals, intialCarRef)
    src = image_parser.valTrackbars()
    set_speed = image_parser.valTrackbar_speed()
    
    image_parser.perspectiveWarp_init(src)
    prevTime = curTime = time.time()
    timer_past = curTime
    cam_thread = Thread(target=image_parser.get_image_continue)
    cam_thread.start()
    stay_time=0
    laser_parser = LASERParser()
    lc_cmd =False
    is_backside= False
    cnt =0
    FL=True
    
    
    timer_ena= False
   
    

    while not rospy.is_shutdown():
        curTime = time.time()
        
        '''ret, img_wlane = image_parser.get_image()
        imgWarpPoints = img_wlane
        if not ret: continue'''

        if not image_parser.saving_ret: continue
        img_wlane = image_parser.saving_img
        imgWarpPoints = img_wlane
        
        fps = 1 / (curTime - prevTime)
        prevTime = curTime
        fps_str = "FPS: %0.1f" % fps
        
        img_wlane = image_parser.image_process(img_wlane)
        
        
        #region trackbar read
        src = image_parser.valTrackbars()
        if image_parser.trackbar_change_flag:
            image_parser.trackbar_change_flag = False
            print("Recalculate perspectiveWarp.")
            image_parser.perspectiveWarp_init(src)
        
        if image_parser.speed_change_flag:
            image_parser.speed_change_flag = False
            set_speed = image_parser.valTrackbar_speed()
            print("Change the speed " + str(set_speed))
        #endregion

        birdView = image_parser.perspectiveWarp(img_wlane, src)

        imgWarpPoints = image_parser.drawPoints(imgWarpPoints, src)
        
        try:
            imgSliding, ploty, left_fit, right_fit, left_fitx, right_fitx = image_parser.sliding_window(birdView, draw_windows=False)

            draw_info = image_parser.general_search(birdView, left_fit, right_fit)

            #curveRad, curveDir = image_parser.measure_lane_curvature(ploty, left_fitx, right_fitx)
            
            deviation, directionDev = image_parser.offCenter(draw_info)
            
            #Servo Steer Level: 0.15(L) - 0.5304(C) - 0.85(R)
            #driving Level: -3000 ~ 3000 RPM
            dst_steer_level = 0.5304 - float(deviation)*(100/100)
            fps_str += " dstStr: %5.2f" % deviation   
            fps_str += " dstStr: %5.2f" % dst_steer_level 
        
            #ctrl_lat.pub_cmd(226, dst_steer_level)  
            cv2.putText(imgWarpPoints, fps_str, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255))

        except Exception as e:
            fps_str += " Lane Error"
            pass

        
        #print(laser_parser.scan_dis)
        
        is_leftside = laser_parser.left_detect
        is_backside = laser_parser.back_detect

        print(is_backside, "!",is_leftside , "!",lc_cmd)

        # if not is_backside and not lc_cmd:
        #     if  laser_parser.scan_dis<1.5:
        #         is_backside =True
        #         print("back!")

        if is_backside == True and is_leftside == False and FL:
            print("fire1")
            lc_cmd = True
            FL = False
            set_speed=300
            timer_past = curTime + 2.0
            print("fire2")
        
        if lc_cmd : #and self.fuck
            print("fire truck!!! lane change \n")
            dst_steer_level=0.65
        # else:
        #     print("wwwwwwwwwwwww")    
            
        if (timer_past < curTime) and timer_past != 0.0:
            timer_past = 0.0
            #timer cycle code
            print("fire3")
            lc_cmd= False
            is_backside = False
            
            print("fire4")
            
        try:
            ctrl_lat.pub_cmd(set_speed*10, dst_steer_level)
            cv2.imshow("Pipe Line 1", imgSliding)
        except:
            pass

        cv2.imshow(image_parser.trackbar_name, imgWarpPoints)

        if cv2.waitKey(1) == 13: break
        
        continue
    image_parser.keep_reading = False
    time.sleep(0.5)
    cam_thread.join()
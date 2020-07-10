#!/usr/bin/env python
# -*- coding: utf-8 -*-

import rospy
from sensor_msgs.msg import LaserScan,PointCloud
from std_msgs.msg import Float64
from vesc_msgs.msg import VescStateStamped
from math import cos,sin,pi
from geometry_msgs.msg import Point32




class simple_controller:
    def __init__(self):
        rospy.init_node('simple_controller',anonymous=True)
        rospy.Subscriber('/scan',LaserScan, self.laser_callback)
        self.motor_pub =rospy.Publisher('commands/motor/speed',Float64,queue_size=1)
        self.servo_pub =rospy.Publisher('commands/servo/position',Float64,queue_size=1)
        self.pcd_pub =rospy.Publisher('Laser2pcd',PointCloud,queue_size=1)

        while not rospy.is_shutdown():
            rospy.spin()
        

    def laser_callback(self, msg):
        
    
        motor_msg=Float64()
   
        motor_msg.data=0
            


      

        self.motor_pub.publish(motor_msg)

       

            

if __name__ == "__main__":
    try:
        test_track=simple_controller()
    except rospy.ROSInterruptException:
      pass
    

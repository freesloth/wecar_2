#!/usr/bin/env python
import rospy
from std_msgs.msg import String

NAME_TOPIC ='/msgs_talk'
NAME_NODE ='pub_node'

if __name__=='__main__':

    pub=rospy.Publisher(NAME_TOPIC,String,queue_size=10)

    rospy.init_node(NAME_NODE,anonymous=True)

    rate=rospy.Rate(10)

    msgs_pub=String()

    while not rospy.is_shutdown():

        msgs_pub.data="hello ROSworld"

        pub.publish(msgs_pub)

        rate.sleep()
import rospy
from std_msgs.msg import String

NAME_TOPIC ='/msgs_talk'
NAME_NODE ='pub_node'

if__name__=='__main__':

    pub=rospy.Publisher(NAME_TOPIC,String,queue=10)

    rospy.init_node(NAME,anonymous=True)

    rate=rospy.Rate(10)

    msgs_pub=String()

    while not rosy.is_shutdown():

        msgs_pub.data="hello ROSworld"

        pub.publish(msgs_pub)

        rate.sleep()
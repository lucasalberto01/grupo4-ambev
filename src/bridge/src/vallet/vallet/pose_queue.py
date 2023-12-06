import rclpy
from enum import Enum
from typing import Any
from queue import Queue
from rclpy.node import Node
from .streamer import Streamer
from vallet_msgs.msg import Log
from std_msgs.msg import String
from .publisher import Publisher
from .subscriber import Subscriber
from geometry_msgs.msg import Pose
from .__init__ import socket_client
from tf_transformations import quaternion_from_euler
from geometry_msgs.msg import Pose, Point, Quaternion


class RobotStatus(Enum):
    FREE = 0
    BUSY = 1


class PoseQueue(Node):
    def __init__(self):
        super().__init__("pose_queue")
        self.enqueue = Subscriber(self, 
                                  "enqueue", 
                                  "/enqueue", 
                                  Pose)
        
        self.status = Subscriber(self, 
                                 "status", 
                                 "/status", 
                                 String)
        
        self.dequeue = Publisher(self, 
                                 "dequeue", 
                                 "/dequeue", 
                                 Pose)
        
        self.logger = Publisher(self, 
                                "log", 
                                "/logs", 
                                Log)
        
        self.streamer = Streamer(self,
                                 socket_client,
                                 "/enqueue",
                                 self.enqueue_pose)
        
        self.enqueue.create_sub(self.enqueue_pose)
        self.status.create_sub(self.status_callback)

        self.queue = Queue()
        self.robot_status = RobotStatus.FREE

    def enqueue_pose(self, msg: Any) -> None:
        self.get_logger().info(f"Enqueuing {msg} on {self.enqueue.topic_name}")
        if isinstance(msg, Pose):
            log_msg = Log(node_name=self.enqueue.topic_name, 
                        action=f'{msg}',
                        unix_time=int(self.get_clock().now().to_msg().sec))
            self.logger.publish(log_msg)

            self.queue.put(msg)

        elif isinstance(msg, dict):
            try:
                x = msg["x"]
                y = msg["y"]
                q_x, q_y, q_z, q_w = quaternion_from_euler(x, y, 0.0)
                pose = Pose(
                    position=Point(x=x, y=y, z=0.0),
                    orientation=Quaternion(x=q_x, y=q_y, z=q_z, w=q_w)
                )

                log_msg = Log(node_name=self.enqueue.topic_name, 
                        action=f'{msg}',
                        unix_time=int(self.get_clock().now().to_msg().sec))
                self.logger.publish(log_msg)

                self.queue.put(pose)
            except ValueError:
                self.get_logger().info("Invalid pose.")
                
    def status_callback(self, msg: String) -> None:
        self.robot_status = RobotStatus.FREE if msg.data == "FREE" else RobotStatus.BUSY

        if self.robot_status == RobotStatus.BUSY:
            self.get_logger().info(f"Robot is busy, waiting for it to be free.")
        elif self.robot_status == RobotStatus.FREE and not self.queue.empty():
            next_pose = self.queue.get()

            log_msg = Log(node_name=self.dequeue.topic_name,
                          action=f'{next_pose}',
                          unix_time=int(self.get_clock().now().to_msg().sec))
            self.logger.publish(log_msg)
            
            self.dequeue.publish(next_pose)

            self.get_logger().info(
                f"Publishing {next_pose} on {self.dequeue.topic_name}")
        elif self.robot_status == RobotStatus.FREE and self.queue.empty():
            self.get_logger().info("Queue is empty, waiting for new poses.")
        else:
            self.get_logger().info("Something went wrong.")


def main(args=None):
    rclpy.init(args=args)
    pose_queue_node = PoseQueue()
    rclpy.spin(pose_queue_node)
    pose_queue_node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
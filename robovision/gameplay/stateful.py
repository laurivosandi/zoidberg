
import logging
logger = logging.getLogger("gameplay")
from managed_threading import ManagedThread
from image_recognition import ImageRecognition, Point
from arduino import Arduino
import math
from time import time

from collections import defaultdict
from config_manager import ConfigManager




def distance(point_a, point_b):
    A = point_a.x * point_a.dist, point_a.y * point_a.dist
    B = point_b.x * point_b.dist, point_b.y * point_b.dist
    dist = ((A[0]-B[0])**2 + (A[1]-B[1])**2) ** 0.5
    return dist

config = ConfigManager("game")

class Gameplay(ManagedThread):
    def __init__(self, *args, **kwargs):
        ManagedThread.__init__(self, *args)
        self.arduino = Arduino() # config read from ~/.robovision/pymata.conf
        self.state = Patrol(self)
        self.recognition = None
        self.closest_edges = []
        self.safe_distance_to_goals = 1.4
        self.config = config

    @property
    def field_id(self):
        return self.config.get_option("global", "field_id", type=str, default='A').get_value()

    @property
    def robot_id(self):
        return self.config.get_option("global", "robot_id", type=str, default='A').get_value()

    @property
    def is_enabled(self):
        return self.config.get_option("global", "gameplay status", type=str, default='disabled').get_value() == 'enabled'

    @property
    def config_goal(self):
        return self.config.get_option("global", "target goal color", type=str, default='blue').get_value()


    @property
    def balls(self):
        balls = []
        goals = []
        if self.own_goal:
            goals.append(self.own_goal)
        if self.target_goal:
            goals.append(self.target_goal)

        too_close = []
        suspicious = []
        for ball in self.recognition.balls:
            if ball[0].suspicious:
                suspicious.append(ball)
                continue

            # for goal in goals:
            #     if distance(ball[0], goal) < 0.3:
            #         too_close.append(ball)
            #         break
            # else:
            balls.append(ball)

        if len(self.recognition.balls) != len(balls + too_close + suspicious):
            logger.info("FUUUCK")

        # logger.info("Normal{} too_cose{} suspicious{}".format(len(balls), len(too_close), len(suspicious)))

        # logger.info("WASD{} {}".format(len(self.recognition.balls), len(balls + too_close)))
        return balls + too_close + suspicious

    @property
    def own_goal(self):
        return self.recognition.goal_yellow if self.config_goal=='blue' else self.recognition.goal_blue
    @property
    def target_goal(self):
        return self.recognition.goal_blue if self.config_goal=='blue' else self.recognition.goal_yellow

    @property
    def has_ball(self):
        return self.arduino.has_ball

    @property
    def target_goal_detla(self):
        if self.target_goal:
            return self.target_goal.angle_deg

    @property
    def target_goal_dist(self):
        if self.target_goal:
            return self.target_goal.dist

    @property
    def too_close(self):
        min_dist = 0.35
        if self.target_goal and self.target_goal.dist < min_dist:
            return True
        if self.own_goal and self.own_goal.dist < min_dist:
            return True

    @property
    def alligned(self):
        # TODO: inverse of this
        if self.target_goal:
            min_angle = 2 if not self.target_goal_dist or self.target_goal_dist>3 else 3
            return abs(self.target_goal_detla) <= min_angle

    @property
    def focus_time(self):
        return 0.1

    @property
    def rest_time(self):
        return 0.1

    @property
    def closest_edge(self):
        if not self.recognition.closest_edge:
            return
        self.closest_edges = self.closest_edges[1:10] + [self.recognition.closest_edge]
        x, y, = 0, 0
        for closest_edge in self.closest_edges:
            x += closest_edge.x
            y += closest_edge.y
        length = (x**2+y**2)**0.5
        return x/length, y/length, length

    @property
    def field_center_angle(self):
        x, y = self.closest_edge[:2]
        angle = math.atan2(-x,-y)
        # logger.info("{:.1f} {:.1f} {:.1f}".format(x,y, angle))

        return Point(-x, -y).angle_deg

    @property
    def flank_is_alligned(self):
        # if self.balls and abs(self.balls[0][0].angle_deg) < 10:
        #     return True

        in_line = self.goal_to_ball_angle

        if in_line and abs(in_line) < 13:
            log_str = "B{:.1f} G{:.1f} | D{:.1f}".format(self.balls[0][0].angle_deg, self.target_goal.angle_deg, in_line)
            #logger.info(log_str)

            return True

    @property
    def goal_to_ball_angle(self):
        import math

        if not self.target_goal or not self.balls:
            logger.info("goal_to_ball_angle {} {}".format(self.target_goal, self.balls))
            return

        ball = self.balls[0][0]
        goal = self.target_goal

        v1 = goal
        v2 = ball

        v1_theta = math.atan2(v1.y, v1.x)
        v2_theta = math.atan2(v2.y, v2.x)

        r = (v2_theta - v1_theta) * (180.0 / 3.141)

        if r > 180:
            r -= 360
        if r < -180:
            r += 360
        return r

    @property
    def to_close_to_edge(self):
        edge = self.closest_edge
        return edge[2]< 0.4
    @property
    def closest_goal_distance(self):
        own, other = self.own_goal, self.target_goal
        distances = []
        if own:
            distances.append(own.dist)
        if other:
            distances.append(other.dist)
        if own or other:
            return min(distances)
        return 0

    @property
    def danger_zone(self):
        edge = self.closest_edge
        return edge[2]< 1.1 or self.closest_goal_distance<1

    @property
    def blind_spot_for_shoot(self):
        return (not self.own_goal or self.own_goal.dist>3.0) and self.closest_edge[2]<1.2


    def align_to_target_goal(self):
        if not self.target_goal:
            return
        if self.target_goal.dist > 0.5:
            for relative, _, _, _, _ in self.balls[1:]:
                if abs(relative.dist*math.sin(relative.angle_rad))<0.08 and abs(relative.angle_deg) < 60 and abs(relative.dist - self.target_goal.dist):
                    self.arduino.set_xyw([1,-1][relative.angle_rad>0]*0.60,0.0,0.0)
                    return

        sign = [1,-1][self.target_goal_detla>0]
        angle = abs(self.target_goal_detla)
        delta = sign * (0.8 if angle > 20 else 0.5 if angle > 5 else 0.2)
        if delta < 0:
            self.arduino.set_abc(delta * 0.05, delta * 0.1, delta*0.8)
        elif delta > 0:
            self.arduino.set_abc(delta * 0.1, delta * 0.05, delta*0.8)

    def rotate(self, degrees):
        delta = degrees/360
        #TODO enable full rotating
        self.arduino.set_xyw(0, 0, -delta)

    def drive_xy(self, x, y):
        self.arduino.set_xyw(y, x, 0)

    def flank_vector(self):
        r = self.goal_to_ball_angle
        if not r:
            logger.info("not flank vector")
            return

        ball = self.balls[0][0]

        sign = [-1, 1][r>0]

        delta_deg = 40 * sign / ball.dist

        delta = math.radians(delta_deg)

        bx, by = ball.x, ball.y
        x = bx * math.cos(delta) - by * math.sin(delta)
        y = bx * math.sin(delta) + by * math.cos(delta)

        angle = math.degrees(math.atan2((y), (x)))
        # logger.info("delta{} angle{} ball{} -> {}".format(round(delta_deg),round(r),round(ball.angle_deg), round(angle)))

        return x,y

    def flank(self):
        flank = self.flank_vector()
        if not flank:
            return

        x, y = flank
        min_speed = 0.80
        max_val = max([abs(x), abs(y)])
        if max_val < min_speed and max_val:
            scaling = min_speed / max_val
            x *= scaling
            y *= scaling

        rotating_sign = [1,-1][self.target_goal_detla>0]
        angle = min(abs(self.target_goal_detla), 30)

        delta = rotating_sign * 0.8 * angle / 30

        self.arduino.set_xyw(y, x, delta)

    def kick(self):
        return self.arduino.kick()

    def stop_moving(self):
        self.arduino.set_abc(0,0,0)

    def drive_to_ball(self):

        if not self.balls:
            return

        ball = self.balls[0][0]
        # logger.info("%f" % ball.dist)

        x, y = ball.x, ball.y
        min_speed = 0.3
        max_val = max([abs(x), abs(y)])
        if max_val < min_speed and max_val:
            scaling = min_speed / max_val
            x *= scaling
            y *= scaling

        w = - ball.angle_deg / 180.0

        self.arduino.set_xyw(y, x, w)


    def drive_away_from_goal(self):

        # logger.info(str([self.own_goal]))
        if self.own_goal and self.target_goal:
            goal = self.own_goal if self.own_goal.dist > self.target_goal.dist else self.target_goal
        else:
            goal = self.own_goal or self.target_goal
        if not goal:
            return

        x, y = goal.x, goal.y

        if goal.dist < 1.5: #self.safe_distance_to_goals:
            x *= -1
            y *= -1

        self.arduino.set_xyw(y, x, 0.5)

    def drive_to_field_center(self):

        if not self.closest_edge:
            return

        x, y, _ = self.closest_edge

        # logger.info("{} == {}?".format(self.field_center_angle, Point(-x, -y).angle_deg))
        self.arduino.set_xyw(-y, -x, 0)

    def step(self, recognition, *args):
        if not recognition:
            return

        self.recognition = recognition
        self.state = self.state.tick()

    def on_enabled(self, *args):
        self.config.get_option("global", "gameplay status", type=str, default='disabled').set_value('enabled')
        self.arduino.set_grabber(True)

    def on_disabled(self, *args):
        self.config.get_option("global", "gameplay status", type=str, default='disabled').set_value('disabled')
        self.arduino.set_grabber(False)
        self.arduino.set_xyw(0, 0, 0)

    def start(self):
        self.arduino.start()
        ManagedThread.start(self)


class StateNode:
    is_recovery = False
    recovery_counter = 0
    recovery_factor = 0.5
    def __init__(self,actor):
        self.transitions = dict(self.exctract_transistions())
        self.actor = actor
        self.time = time()
        self.timers = defaultdict(time)

    @property
    def forced_recovery_time(self):
        logger.info("DEBUG forced_recovery_time: %f" % (time()-self.time))
        return self.time + min(self.recovery_counter*self.recovery_factor, 5)>time()


    def exctract_transistions(self):
        return [i for i in self.__class__.__dict__.items() if 'VEC' in i[0] ]

    def transition(self):
        for name, vector in self.transitions.items():
            result = vector(self)
            if result:
                logger.info("\n%s -> %s" % (name, result.__class__.__name__))
                return result
        return self

    def animate(self):
        print("I exist")

    def tick(self):
        next_state = self.transition() or self
        if next_state != self:
            StateNode.recovery_counter+=next_state.is_recovery
            if self.actor.has_ball:
                StateNode.recovery_counter = 0
            logger.info('StateNode.recovery_counter: %s'% str(StateNode.recovery_counter))

            self.actor.stop_moving() # PRE EMPTIVE, should not cause any issues TM
            logger.info(str(next_state))
        else:  #  TODO: THis causes latency, maybe ?
            self.animate()
        return next_state

    def __str__(self):
        return str(self.__class__.__name__)


class Patrol(StateNode):
    def animate(self):
        self.actor.drive_to_field_center()

    def VEC_SEE_BALLS_AND_CAN_FLANK(self):
        if self.actor.balls and not self.actor.danger_zone:
            logger.info("Robot in %s VEC_SEE_BALLS_AND_CAN_FLANK" % str(self))
            return Flank(self.actor)

    def VEC_SEE_BALLS_AND_SHOULD_DRIVE(self):
        if self.actor.balls and self.actor.danger_zone:
            logger.info("Robot in %s VEC_SEE_BALLS_AND_SHOULD_DRIVE" % str(self))
            return Flank(self.actor)

    def VEC_HAS_BALL(self):
        if self.actor.has_ball:
            logger.info("Robot in %s VEC_HAS_BALL" % str(self) )
            return FindGoal(self.actor)

    def VEC_TOO_CLOSE(self):
        if self.actor.too_close:
            logger.info("Robot in %s VEC_TOO_CLOSE" % str(self))
            return Penalty(self.actor)
    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)

class Flank(StateNode):
    def animate(self):
        # if not self.actor.flank_is_alligned:
        self.actor.flank()
        # logger.info(self.actor.balls)

    def VEC_HAS_BALL(self):
        if self.actor.has_ball:
            logger.info("Robot in %s VEC_HAS_BALL"  % str(self))
            return FindGoal(self.actor)

    def VEC_LOST_SIGHT(self):
        if not self.actor.balls:
            logger.info("Robot in %s VEC_LOST_SIGHT"  % str(self))
            return Patrol(self.actor)

    def VEC_LOST_GOAL(self):
        if not self.actor.target_goal:
            logger.info("Robot in %s VEC_LOST_GOAL" % str(self))
            return Drive(self.actor)

    def VEC_TOO_CLOSE(self):
        if self.actor.too_close:
            logger.info("Robot in %s VEC_TOO_CLOSE" % str(self))
            return Penalty(self.actor)

    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)

    def VEC_IN_DANGER_ZONE(self):
        if self.actor.danger_zone and self.actor.balls:
            logger.info("Robot in %s VEC_IN_DANGER_ZONE" % str(self))
            return Drive(self.actor)

    def VEC_FLANK_DONE(self):
        if self.actor.flank_is_alligned:
            if "VEC_FLANK_DONE" not in self.timers:
                self.timers["VEC_FLANK_DONE"] = time()
            elif time() > self.timers["VEC_FLANK_DONE"] + 0.3:
                logger.info("Robot in %s VEC_FLANK_DONE" % str(self))
                return Drive(self.actor)
        else:
            self.timers.pop('VEC_FLANK_DONE', None)

    #def VEC_LOST_GOAL_BUT_HAVE_BALL -> Drive?


class Drive(StateNode):
    def animate(self):
        self.actor.drive_to_ball()


    def VEC_HAS_BALL_IN_BLIND_SPOT(self):
        if self.actor.has_ball and self.actor.blind_spot_for_shoot:
            logger.info("Robot in %s VEC_HAS_BALL_IN_BLIND_SPOT" % str(self))
            return OutOfBounds(self.actor)

    def VEC_HAS_BALL(self):
        if self.actor.has_ball and not self.actor.blind_spot_for_shoot:
            logger.info("Robot in %s VEC_HAS_BALL" % str(self))
            return FindGoal(self.actor)

    def VEC_LOST_SIGHT(self):
        if not self.actor.has_ball and not self.actor.balls:
            logger.info("Robot in %s VEC_LOST_SIGHT" % str(self))
            return Patrol(self.actor)

    def VEC_TOO_CLOSE(self):
        if self.actor.too_close:
            logger.info("Robot in %s VEC_TOO_CLOSE" % str(self))
            return Penalty(self.actor)

    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)

class Escape(StateNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.actor.balls:
            ball = self.actor.balls[0][0]
            self.escape_vector=-ball.x, -ball.y
        else:
            self.escape_vector = None

    def animate(self):
        if self.escape_vector:
            self.actor.drive_xy(*self.escape_vector)


class FindGoal(StateNode):
    def animate(self):
        self.actor.drive_to_field_center()

    def VEC_HAS_GOAL(self):
        if self.actor.target_goal:
            logger.info("Robot in %s VEC_HAS_GOAL" % str(self))
            return TargetGoal(self.actor)

    def VEC_LOST_BALL(self):
        # logger.info("Robot in FindGoal BALL STATE {}".format(self.actor.has_ball))
        if not self.actor.has_ball:
            logger.info("Robot in %s VEC_LOST_BALL" % str(self))
            return Patrol(self.actor)

class DriveToCenter(StateNode):
    is_recovery = True

    def animate(self):
        self.actor.drive_to_field_center()

    def VEC_LOST_BALL(self):
        if not self.actor.has_ball:
            logger.info("Robot in %s VEC_HAS_GOAL" % str(self))
            return Patrol(self.actor)

    def VEC_IN_CENTER(self):
        logger.info("Robot in DriveToCenter time {} {}".format(self.time + 1.5, time()))
        if self.time + 1.5 > time():
            logger.info("Robot in %s IN_CENTER" % str(self))
            return TargetGoal(self.actor)

    def VEC_TOO_CLOSE(self):
        if self.actor.too_close:
            logger.info("Robot in %s VEC_TOO_CLOSE" % str(self))
            return Penalty(self.actor)

    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)



class TargetGoal(StateNode):
    VISITS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        TargetGoal.VISITS.append(time())
        TargetGoal.VISITS = list(filter(lambda x: x + 0.5 > time(), TargetGoal.VISITS))

    def animate(self):
        self.actor.align_to_target_goal()
        #self.actor.drive_away_from_goal()

    def VEC_TO_MUTCH_VISITS(self):
        # return
        if len(TargetGoal.VISITS) > 4:
            logger.info("Robot in %s VEC_TO_MUTCH_VISITS" % str(self))
            return DriveToCenter(self.actor)

    def VEC_POINTED_AT_GOAL(self):
        # return
        if self.actor.alligned:
            logger.info("Robot in %s VEC_POINTED_AT_GOAL" % str(self))
            return Focus(self.actor)

    def VEC_LOST_BALL(self):
        if not self.actor.has_ball:
            logger.info("Robot in %s VEC_LOST_BALL" % str(self))
            return Patrol(self.actor)

    def VEC_LOST_GOAL(self):
        # logger.info("Robot in FindGoal BALL STATE {}".format(self.actor.has_ball))
        if not self.actor.target_goal:
            logger.info("Robot in %s VEC_LOST_GOAL" % str(self))
            return FindGoal(self.actor)

    def VEC_TOO_CLOSE(self):
        if self.actor.too_close:
            logger.info("Robot in %s VEC_TOO_CLOSE" % str(self))
            return Penalty(self.actor)

    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)


class Focus(StateNode):

    def animate(self):
        self.actor.stop_moving()
        pass

    def VEC_NOT_ALLIGNED(self):
        if not self.actor.alligned:
            logger.info("Robot in %s VEC_NOT_ALLIGNED" % str(self))
            return TargetGoal(self.actor)

    def VEC_LOST_BALL(self):
        if not self.actor.has_ball:
            logger.info("Robot in %s VEC_LOST_BALL" % str(self))
            return Patrol(self.actor)

    def VEC_READY_TO_SHOOT(self):
        if self.actor.alligned and self.actor.has_ball and self.time + self.actor.focus_time < time():
            logger.info("Robot in %s VEC_READY_TO_SHOOT" % str(self))
            return Shoot(self.actor)


class Shoot(StateNode):

    def animate(self):
        self.actor.kick()

    def VEC_DONE_SHOOTING(self):
        if not self.actor.has_ball:
            logger.info("Robot in %s VEC_DONE_SHOOTING" % str(self))
            return PostShoot(self.actor)

class PostShoot(StateNode):

    def animate(self):
        pass

    def VEC_DONE_LOLLYGAGGING(self):
        if self.time + self.actor.focus_time < time():
            logger.info("Robot in %s VEC_DONE_LOLLYGAGGING" % str(self))
            return Patrol(self.actor)


class OutOfBounds (StateNode):
    is_recovery = True
    def animate(self):
        if self.actor.has_ball and abs(self.actor.field_center_angle) > 15 and self.time + 0.5 > time():
            self.actor.rotate(self.actor.field_center_angle)
        else:
            self.actor.drive_to_field_center()

    def VEC_DONE_CENTERING(self):
        _, _, length = self.actor.closest_edge
        if length > 1.2 and not self.forced_recovery_time:
            return Patrol(self.actor)


class Penalty(StateNode):

    VISITS = []
    is_recovery = True
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Penalty.VISITS.append(time())
        Penalty.VISITS = list(filter(lambda x: x + 2 > time(), Penalty.VISITS))

    def animate(self):
        self.actor.drive_away_from_goal()
#       logger.info("Blue {}; Yellow {}".format(self.actor.target_goal.dist,self.actor.own_goal.dist))

    def VEC_ENOUGH_FAR(self):
        own, other = self.actor.own_goal, self.actor.target_goal
        safe_dist = self.actor.safe_distance_to_goals
        if (not own or own.dist >= safe_dist) and (not other or other.dist >= safe_dist) and not self.forced_recovery_time:
            logger.info("Robot in %s VEC_ENOUGH_FAR" % str(self))
            return Patrol(self.actor)

    def VEC_TO_CLOSE_TO_EDGE(self):
        if self.actor.to_close_to_edge:
            logger.info("Robot in %s VEC_TO_CLOSE_TO_EDGE" % str(self))
            return OutOfBounds(self.actor)

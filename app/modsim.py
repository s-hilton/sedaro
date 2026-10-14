# MODELING & SIMULATION

import math
from random import random

import numpy as np

from mesh import inertia_from_dict

def vector(d):
    return np.array([d['x'], d['y'], d['z']], dtype=float)

def to_dict(v):
    return {'x': v[0], 'y': v[1], 'z': v[2]}

def rotation_matrix(attitude):
    """Rotation matrix taking body-frame vectors to the inertial frame, from a unit quaternion."""
    w, x, y, z = attitude['w'], attitude['x'], attitude['y'], attitude['z']
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])

def attitude_from_euler(yaw, pitch, roll):
    """
    Unit quaternion (body to inertial) for aerospace Z-Y-X Euler angles in degrees: rotate by `yaw`
    about z, then by `pitch` about the new y axis, then by `roll` about the new x axis.
    """
    yaw, pitch, roll = (math.radians(a) / 2 for a in (yaw, pitch, roll))
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    return {
        'w': cy * cp * cr + sy * sp * sr,
        'x': cy * cp * sr - sy * sp * cr,
        'y': cy * sp * cr + sy * cp * sr,
        'z': sy * cp * cr - cy * sp * sr,
    }

def inertial_inertia(inertia, attitude):
    """The body's inertia tensor about its center of mass, expressed in the inertial frame."""
    rotation = rotation_matrix(attitude)
    return rotation @ inertia_from_dict(inertia) @ rotation.T

def quadrupole_gradient(r, inertia):
    """
    Gradient with respect to `r` of the second-order (MacCullagh) term of an extended body's
    gravitational potential, (tr(I) - 3 r_hat' I r_hat) / (2 |r|^3), where `I` is the body's
    inertia tensor in the inertial frame and `r` points from the body's center of mass to the
    point mass. Zero for a point mass (I = 0).
    """
    distance = np.linalg.norm(r)
    r_hat = r / distance
    return -3 / (2 * distance**5) * (np.trace(inertia) * r + 2 * inertia @ r - 5 * (r_hat @ inertia @ r_hat) * r)

def propagate_velocity(time_step, position, velocity, mass, inertia, attitude,
                       other_position, m_other, other_inertia, other_attitude):
    """Propagate the velocity of the agent from `time` to `time + timeStep`."""
    # Use law of gravitation to update velocity
    r_self = vector(position)
    v_self = vector(velocity)
    r_other = vector(other_position)

    r = r_self - r_other
    dvdt = -m_other * r / np.linalg.norm(r)**3
    # Extended bodies: the potential's quadrupole terms, from the shape of each body, add a force
    # equal and opposite on the two bodies. For point masses (zero inertia) this term is zero.
    shape_force = m_other * quadrupole_gradient(r, inertial_inertia(inertia, attitude)) \
        + mass * quadrupole_gradient(r, inertial_inertia(other_inertia, other_attitude))
    dvdt = dvdt + shape_force / mass
    v_self = v_self + dvdt * time_step

    return to_dict(v_self)

def propagate_position(time_step, position, velocity):
    """Propagate the position of the agent from `time` to `time + timeStep`."""
    # Apply velocity to position
    r_self = vector(position)
    v_self = vector(velocity)

    r_self = r_self + v_self * time_step

    return to_dict(r_self)

def gravity_gradient_torque(inertia, attitude, position, other_position, m_other):
    """
    Torque on an extended body from a point mass, in the body frame:
    3 m_other / |r|^5 * (r x I r), with `r` the direction to the other body in the body frame.
    It turns the body's axis of least inertia toward the other body.
    """
    r = rotation_matrix(attitude).T @ (vector(other_position) - vector(position))
    return 3 * m_other / np.linalg.norm(r)**5 * np.cross(r, inertia @ r)

def quaternion_rate(q, omega):
    """Time derivative of a body-to-inertial quaternion [w, x, y, z] for body-frame angular velocity."""
    w, x, y, z = q
    p, r, s = omega
    return 0.5 * np.array([
        -x * p - y * r - z * s,
        w * p + y * s - z * r,
        w * r - x * s + z * p,
        w * s + x * r - y * p,
    ])

def rotate_rigid_body(time_step, angular_velocity, attitude, inertia, position, other_position, m_other):
    """
    Advance a rigid body's rotation over one step and return its body-frame angular velocity and
    attitude at the end of the step.

    Like the translational update (velocity kicked by the force, then position drifted with the new
    velocity), the gravity-gradient torque at the start of the step first kicks the angular velocity,
    and then the torque-free rotation (Euler's equations, I dw/dt = -w x I w, together with the
    attitude quaternion) is integrated with RK4. The kick-then-drift split keeps gravity-gradient
    oscillations from growing over time, and RK4 keeps a freely tumbling body accurate.
    """
    inertia = inertia_from_dict(inertia)
    omega = vector(angular_velocity)
    q = np.array([attitude['w'], attitude['x'], attitude['y'], attitude['z']], dtype=float)
    if inertia.any():
        inverse = np.linalg.inv(inertia)
        torque = gravity_gradient_torque(inertia, attitude, position, other_position, m_other)
        omega = omega + time_step * inverse @ torque
        dwdt = lambda w: -inverse @ np.cross(w, inertia @ w)
    else:
        # A point mass has no rotational dynamics; any angular velocity stays constant.
        dwdt = lambda w: np.zeros(3)

    def rates(w, q):
        return dwdt(w), quaternion_rate(q, w)

    k1 = rates(omega, q)
    k2 = rates(omega + time_step / 2 * k1[0], q + time_step / 2 * k1[1])
    k3 = rates(omega + time_step / 2 * k2[0], q + time_step / 2 * k2[1])
    k4 = rates(omega + time_step * k3[0], q + time_step * k3[1])
    omega = omega + time_step / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0])
    q = q + time_step / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1])
    q = q / np.linalg.norm(q)
    return to_dict(omega), {'w': q[0], 'x': q[1], 'y': q[2], 'z': q[3]}

def propagate_angular_velocity(time_step, angular_velocity, attitude, inertia, position, other_position, m_other):
    """Propagate the body-frame angular velocity from `time` to `time + timeStep`."""
    return rotate_rigid_body(time_step, angular_velocity, attitude, inertia, position, other_position, m_other)[0]

def propagate_attitude(time_step, angular_velocity, attitude, inertia, position, other_position, m_other):
    """Propagate the attitude quaternion (body to inertial) from `time` to `time + timeStep`."""
    return rotate_rigid_body(time_step, angular_velocity, attitude, inertia, position, other_position, m_other)[1]

def propagate_mass(mass):
    return mass

def identity(arg):
    return arg

# Fraction of the two-body dynamical time to advance per step (~2*pi/ETA steps per circular orbit).
TIMESTEP_FRACTION = 0.02
# Largest rotation of a spinning body per step, in radians.
MAX_ROTATION_PER_STEP = 0.05

def timestep_manager(position, velocity, mass, other_position, other_velocity, m_other, angular_velocity):
    """Compute the length of this simulation step from the state at the start of the step.

    The step is a fixed fraction of the shorter of two timescales:
    - the two-body dynamical time sqrt(r^3 / (m + m_other)), so it shrinks as the bodies approach
      (where the force changes fastest) and scales with the system, and
    - the crossing time r / |relative velocity|, so the bodies move only a small fraction of their
      separation per step. Without it, bodies flying apart on an unbound path take steps that grow
      faster than their separation, and time runs away to infinity within a few hundred steps.
    For a circular orbit the two are equal. Both are symmetric in the two bodies, so both agents
    choose the same step. A spinning body also limits its step so it turns at most
    MAX_ROTATION_PER_STEP per step.
    """
    separation = np.linalg.norm(vector(position) - vector(other_position))
    speed = np.linalg.norm(vector(velocity) - vector(other_velocity))
    timescale = np.sqrt(separation**3 / (mass + m_other))
    if speed > 0:
        timescale = min(timescale, separation / speed)
    step = TIMESTEP_FRACTION * timescale
    spin = np.linalg.norm(vector(angular_velocity))
    if spin > 0:
        step = min(step, MAX_ROTATION_PER_STEP / spin)
    return step

def time_manager(time, timeStep):
    """Compute the time for the next simulation step for the agent"""
    return time + timeStep

'''
NOTE: Declare what agents should exist, what functions should be run to update their state, 
    and bind the consumed arguments and produced results to each other.

Query syntax:
- `<variableName>` will do a dictionary lookup of `variableName` in the current state of the agent
   the query is running for.
- prev!(<query>)` will get the value of `query` from the previous step of simulation.
- `agent!(<agentId>)` will get the most recent state produced by `agentId`.
- `<query>.<name>` will evaluate `query` and then look up `name` in the resulting dictionary.
'''

def rigid_body(other):
    """
    State managers for a rigid body attracted by the agent `other`. Its state is its center-of-mass
    `position` and `velocity`, `mass`, `inertia` (about the center of mass, in the body frame; all
    zeros for a point mass), `attitude` (unit quaternion, body to inertial) and body-frame
    `angularVelocity`.
    """
    return [
        {
            'consumed': f'''(
                timeStep,
                prev!(position),
                prev!(velocity),
                prev!(mass),
                prev!(inertia),
                prev!(attitude),
                agent!({other}).position,
                agent!({other}).mass,
                agent!({other}).inertia,
                agent!({other}).attitude,
            )''',
            'produced': '''velocity''',
            'function': propagate_velocity,
        },
        {
            'consumed': '''(
                timeStep,
                prev!(position),
                velocity,
            )''',
            'produced': '''position''',
            'function': propagate_position,
        },
        {
            'consumed': f'''(
                timeStep,
                prev!(angularVelocity),
                prev!(attitude),
                prev!(inertia),
                prev!(position),
                agent!({other}).position,
                agent!({other}).mass,
            )''',
            'produced': '''angularVelocity''',
            'function': propagate_angular_velocity,
        },
        {
            'consumed': f'''(
                timeStep,
                prev!(angularVelocity),
                prev!(attitude),
                prev!(inertia),
                prev!(position),
                agent!({other}).position,
                agent!({other}).mass,
            )''',
            'produced': '''attitude''',
            'function': propagate_attitude,
        },
        {
            'consumed': '''(
                prev!(mass),
            )''',
            'produced': '''mass''',
            'function': propagate_mass,
        },
        {
            'consumed': '''(
                prev!(inertia),
            )''',
            'produced': '''inertia''',
            'function': identity,
        },
        {
            'consumed': '''(
                prev!(time),
                timeStep
            )''',
            'produced': '''time''',
            'function': time_manager,
        },
        {
            'consumed': f'''(
                prev!(position),
                prev!(velocity),
                prev!(mass),
                agent!({other}).position,
                agent!({other}).velocity,
                agent!({other}).mass,
                prev!(angularVelocity),
            )''',
            'produced': '''timeStep''',
            'function': timestep_manager,
        }
    ]

agents = {
    'Body1': rigid_body('Body2'),
    'Body2': rigid_body('Body1'),
}

# A point mass: no extent, so no inertia, rotation or shape effects.
POINT_MASS = {
    'inertia': {'xx': 0, 'yy': 0, 'zz': 0, 'xy': 0, 'xz': 0, 'yz': 0},
    'attitude': {'w': 1, 'x': 0, 'y': 0, 'z': 0},
    'angularVelocity': {'x': 0, 'y': 0, 'z': 0},
}

# NOTE: initial values are set here. we intentionally separate the data from the functions operating on it.
data = {
    'Body1': {
        'timeStep': 0.01,
        'time': 0.0,
        'position': {'x': -0.73, 'y': 0, 'z': 0},
        'velocity': {'x': 0, 'y': -0.0015, 'z': 0},
        'mass': 1,
        **POINT_MASS,
    },
    'Body2': {
        'timeStep': 0.01,
        'time': 0.0,
        'position': {'x': 60.34, 'y': 0, 'z': 0},
        'velocity': {'x': 0, 'y': 0.13 , 'z': 0},
        'mass': 0.123,
        **POINT_MASS,
    }
}

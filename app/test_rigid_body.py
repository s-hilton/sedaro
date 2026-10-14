#!/usr/bin/env python3

"""
NOTE: Tests for rigid-body dynamics. First build the `queries` binary with `cargo build --release`,
then run from `app/` with `python3 -m unittest test_rigid_body`.
"""

import copy
import math
import unittest

import numpy as np

import modsim
from mesh import inertia_from_dict, inertia_to_dict
from modsim import (gravity_gradient_torque, inertial_inertia, propagate_velocity, quadrupole_gradient,
                    rotate_rigid_body, rotation_matrix, vector)
from simulator import Simulator
from store import QRangeStore

ORIGIN = {'x': 0, 'y': 0, 'z': 0}
IDENTITY = {'w': 1, 'x': 0, 'y': 0, 'z': 0}
POINT = inertia_to_dict(np.zeros((3, 3)))
FAR = {'x': 1e9, 'y': 0, 'z': 0}


def box_inertia(mass, a, b, c):
    return inertia_to_dict(mass * np.diag([b * b + c * c, a * a + c * c, a * a + b * b]) / 12)


def yaw(degrees):
    half = math.radians(degrees) / 2
    return {'w': math.cos(half), 'x': 0, 'y': 0, 'z': math.sin(half)}


def run(init, iterations):
    store = QRangeStore()
    Simulator(store, copy.deepcopy(init)).simulate(iterations)
    states = {agent: [state] for agent, state in init.items()}
    for _, _, value in store.store[1:]:
        for agent, state in value.items():
            states[agent].append(state)
    return states


def lockstep(states):
    """Pairs of (Body1, Body2) states at the same time."""
    body1 = {s['time']: s for s in states['Body1']}
    return [(body1[s['time']], s) for s in states['Body2'] if s['time'] in body1]


def totals(s1, s2):
    """Total energy and angular momentum of the two-body system, to the same order as the dynamics."""
    m1, m2 = s1['mass'], s2['mass']
    r1, r2, v1, v2 = (vector(s1['position']), vector(s2['position']), vector(s1['velocity']), vector(s2['velocity']))
    I1, I2 = inertial_inertia(s1['inertia'], s1['attitude']), inertial_inertia(s2['inertia'], s2['attitude'])
    Ib1, Ib2 = inertia_from_dict(s1['inertia']), inertia_from_dict(s2['inertia'])
    w1, w2 = vector(s1['angularVelocity']), vector(s2['angularVelocity'])
    d = r1 - r2
    distance = np.linalg.norm(d)
    d_hat = d / distance
    shape = lambda I: (np.trace(I) - 3 * d_hat @ I @ d_hat) / (2 * distance**3)
    potential = -m1 * m2 / distance - m2 * shape(I1) - m1 * shape(I2)
    energy = 0.5 * (m1 * v1 @ v1 + m2 * v2 @ v2 + w1 @ Ib1 @ w1 + w2 @ Ib2 @ w2) + potential
    momentum = (m1 * np.cross(r1, v1) + m2 * np.cross(r2, v2)
                + rotation_matrix(s1['attitude']) @ Ib1 @ w1 + rotation_matrix(s2['attitude']) @ Ib2 @ w2)
    return energy, momentum


class ShapeGravityTest(unittest.TestCase):
    def dumbbell_error(self, distance, use_shape):
        # Two half masses at +-0.5 on x, versus the monopole (+ quadrupole) approximation.
        mass = 1.0
        inertia = inertia_to_dict(np.diag([0, mass / 4, mass / 4])) if use_shape else POINT
        p = distance * np.array([0.6, 0.48, 0.64])
        exact = sum(-(mass / 2) * (p - q) / np.linalg.norm(p - q)**3 for q in ([0.5, 0, 0], [-0.5, 0, 0]))
        # Velocity change over a unit step of a light point mass at p.
        dv = propagate_velocity(1.0, dict(zip('xyz', p)), ORIGIN, 1e-3, POINT, IDENTITY,
                                ORIGIN, mass, inertia, IDENTITY)
        return np.linalg.norm(vector(dv) - exact) / np.linalg.norm(exact)

    def test_quadrupole_matches_exact_extended_body(self):
        for distance in (5, 10, 20):
            point, shaped = self.dumbbell_error(distance, False), self.dumbbell_error(distance, True)
            # The point-mass error falls as (L/r)^2, the remaining error as (L/r)^4.
            self.assertLess(shaped, point / 50)
        self.assertLess(self.dumbbell_error(10, True), 2e-5)

    def test_shape_forces_are_equal_and_opposite(self):
        bar, block = box_inertia(0.5, 4, 1, 1), box_inertia(2.0, 3, 2, 1)
        a = {'x': 1.0, 'y': -2.0, 'z': 0.5}
        b = {'x': 9.0, 'y': 3.0, 'z': -1.0}
        dv_a = propagate_velocity(1.0, a, ORIGIN, 0.5, bar, yaw(20), b, 2.0, block, yaw(-50))
        dv_b = propagate_velocity(1.0, b, ORIGIN, 2.0, block, yaw(-50), a, 0.5, bar, yaw(20))
        np.testing.assert_allclose(0.5 * vector(dv_a), -2.0 * vector(dv_b), rtol=1e-12)

    def test_point_masses_have_no_shape_force(self):
        np.testing.assert_array_equal(quadrupole_gradient(np.array([3.0, 4.0, 0]), np.zeros((3, 3))), 0)


class RotationTest(unittest.TestCase):
    def test_gravity_gradient_turns_long_axis_toward_other_body(self):
        # A bar along body x, rotated 10 degrees about z away from the direction to the other body
        # (+x), is pushed back toward it: negative torque about z.
        bar = inertia_from_dict(box_inertia(1, 4, 1, 1))
        torque = gravity_gradient_torque(bar, yaw(10), ORIGIN, {'x': 50, 'y': 0, 'z': 0}, 1.0)
        self.assertLess(torque[2], 0)
        self.assertAlmostEqual(torque[0], 0)
        self.assertAlmostEqual(torque[1], 0)

    def test_free_tumbling_conserves_energy_and_angular_momentum(self):
        inertia = {'xx': 1.0, 'yy': 2.0, 'zz': 3.0, 'xy': 0.3, 'xz': 0, 'yz': 0}
        I = inertia_from_dict(inertia)
        omega, attitude = {'x': 0.1, 'y': 0.5, 'z': 0.05}, IDENTITY
        L0 = rotation_matrix(attitude) @ I @ vector(omega)
        E0 = vector(omega) @ I @ vector(omega) / 2
        for _ in range(2000):  # ~16 revolutions
            step = 0.05 / np.linalg.norm(vector(omega))
            omega, attitude = rotate_rigid_body(step, omega, attitude, inertia, ORIGIN, FAR, 0.0)
        L1 = rotation_matrix(attitude) @ I @ vector(omega)
        self.assertLess(np.linalg.norm(L1 - L0) / np.linalg.norm(L0), 1e-6)
        self.assertLess(abs(vector(omega) @ I @ vector(omega) / 2 - E0) / E0, 1e-7)

    def test_point_mass_does_not_rotate(self):
        omega, attitude = rotate_rigid_body(5.0, ORIGIN, IDENTITY, POINT, ORIGIN, {'x': 10, 'y': 0, 'z': 0}, 1.0)
        self.assertEqual(attitude, {'w': 1, 'x': 0, 'y': 0, 'z': 0})
        np.testing.assert_array_equal(vector(omega), 0)


class SimulationTest(unittest.TestCase):
    def test_point_masses_unaffected(self):
        # Bodies without extent follow the plain point-mass equations: compare one step by hand.
        states = run(modsim.data, 1)
        b1, b2 = modsim.data['Body1'], modsim.data['Body2']
        r = vector(b1['position']) - vector(b2['position'])
        step = states['Body1'][1]['timeStep']
        expected = vector(b1['velocity']) - b2['mass'] * r / np.linalg.norm(r)**3 * step
        np.testing.assert_array_equal(vector(states['Body1'][1]['velocity']), expected)
        self.assertEqual(states['Body1'][1]['attitude'], IDENTITY)

    def test_bodies_flying_apart_keep_finite_steps(self):
        # Body2 above escape speed: the bodies separate forever. Steps must stay finite (time once
        # ran away to infinity here) and energy must stay conserved relative to the motion's scale.
        init = copy.deepcopy(modsim.data)
        init['Body2'].update(mass=0.0123, velocity={'x': 0, 'y': 0.3, 'z': 0})
        pairs = lockstep(run(init, 500))
        self.assertEqual(len(pairs), 501)
        self.assertTrue(all(math.isfinite(s2['time']) for _, s2 in pairs))
        kinetic = lambda s: 0.5 * s['mass'] * vector(s['velocity']) @ vector(s['velocity'])
        scale = kinetic(pairs[0][0]) + kinetic(pairs[0][1])
        E0 = totals(*pairs[0])[0]
        for s1, s2 in pairs:
            self.assertLess(abs(totals(s1, s2)[0] - E0) / scale, 1e-2)
        separation = np.linalg.norm(vector(pairs[-1][0]['position']) - vector(pairs[-1][1]['position']))
        self.assertGreater(separation, 1000)

    def test_extended_bodies_conserve_energy_and_angular_momentum(self):
        init = copy.deepcopy(modsim.data)
        init['Body1'].update(inertia=box_inertia(1, 15, 10, 5))
        init['Body2'].update(inertia=box_inertia(0.123, 20, 2, 2), attitude=yaw(30))
        pairs = lockstep(run(init, 500))
        self.assertEqual(len(pairs), 501)
        E0, L0 = totals(*pairs[0])
        for s1, s2 in pairs:
            E, L = totals(s1, s2)
            self.assertLess(abs((E - E0) / E0), 1e-2)
            self.assertLess(np.linalg.norm(L - L0) / np.linalg.norm(L0), 1e-12)

    def test_libration_period_matches_theory(self):
        # A bar on a circular orbit, co-rotating, tilted 5 degrees from the line to the other body,
        # oscillates about it with angular frequency n * sqrt(3 (m1 / M) (Iyy - Ixx) / Izz).
        m1, m2, R = 1.0, 0.123, 60.0
        M = m1 + m2
        n = math.sqrt(M / R**3)
        bar = box_inertia(m2, 4, 1, 1)
        init = copy.deepcopy(modsim.data)
        init['Body1'].update(mass=m1, position={'x': -m2 / M * R, 'y': 0, 'z': 0}, velocity={'x': 0, 'y': -m2 / M * n * R, 'z': 0})
        init['Body2'].update(mass=m2, position={'x': m1 / M * R, 'y': 0, 'z': 0}, velocity={'x': 0, 'y': m1 / M * n * R, 'z': 0},
                             inertia=bar, attitude=yaw(5), angularVelocity={'x': 0, 'y': 0, 'z': n})
        times, angles = [], []
        for s1, s2 in lockstep(run(init, 1500)):
            to_other = vector(s1['position']) - vector(s2['position'])
            axis = rotation_matrix(s2['attitude']) @ np.array([1.0, 0, 0])
            times.append(s2['time'])
            angle = math.degrees(math.atan2(np.cross(to_other, axis)[2], to_other @ axis))
            angles.append((angle + 90) % 180 - 90)  # the bar's axis points both ways
        crossings = [times[i - 1] + (times[i] - times[i - 1]) * angles[i - 1] / (angles[i - 1] - angles[i])
                     for i in range(1, len(angles)) if (angles[i - 1] > 0) != (angles[i] > 0)]
        measured = 2 * np.mean(np.diff(crossings))
        theory = 2 * math.pi / (n * math.sqrt(3 * (m1 / M) * (bar['yy'] - bar['xx']) / bar['zz']))
        self.assertGreater(len(crossings), 10)
        self.assertAlmostEqual(measured / theory, 1, delta=0.01)
        # The oscillation stays bounded instead of growing.
        self.assertLess(max(abs(a) for a in angles), 7.5)


if __name__ == '__main__':
    unittest.main()

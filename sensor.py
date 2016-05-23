import abc

import numpy as np
import scipy.stats


class Sensor(metaclass=abc.ABCMeta):

	def __init__(self, position, pseudo_random_numbers_generator):

		# position is saved for later use
		self.position = position

		# pseudo random numbers generator
		self._pseudo_random_numbers_generator = pseudo_random_numbers_generator

	@abc.abstractmethod
	def detect(self, target_pos):

		pass

	@abc.abstractmethod
	def likelihood(self, observation, positions):

		""" It computes the likelihoods of several positions.
		
		Parameters
		----------
		observation: float
			the observation whose probability is computed
		positions: numpy array
			positions of several particles
		"""
		pass


class BinarySensor(Sensor):

	def __init__(
			self, position, radius, probability_of_detection_within_the_radius=0.9, probability_of_false_alarm=0.01,
			pseudo_random_numbers_generator=np.random.RandomState()):

		super().__init__(position, pseudo_random_numbers_generator)

		# the distance within reach of the sensor
		self._threshold = radius

		# the probability of (correct) detection
		self._probDetection = probability_of_detection_within_the_radius

		# the probability of false alarm
		self._probFalseAlarm = probability_of_false_alarm

		# for the sake of convenience when computing the likelihood: we keep an array with the probability mass function
		# of the observations conditional on the target being close enough (it depends on the threshold)...
		# self._pmfObservationsWhenClose[x] = p(observation=x | |<target position> - <sensor position>| < threshold)
		self._pmfObservationsWhenClose = np.array(
			[1-probability_of_detection_within_the_radius, probability_of_detection_within_the_radius])

		# ...and that of the observations conditional on the target being far
		self._pmfObservationsWhenFar = np.array([1-probability_of_false_alarm, probability_of_false_alarm])

	def detect(self, target_pos):

		distance = np.linalg.norm((self.position - target_pos))

		if distance < self._threshold:
			return self._pseudo_random_numbers_generator.rand() < self._probDetection
		else:
			return self._pseudo_random_numbers_generator.rand() < self._probFalseAlarm

	def likelihood(self, observation, positions):

		# the distances to ALL the positions are computed
		distances = np.linalg.norm(np.subtract(positions, self.position), axis=0)

		# an empty array with the same dimensions as distances is created
		likelihoods = np.empty_like(distances)

		# the likelihood for a given observation is computed using probability mass function if the target
		# is within the reach of the sensor...
		likelihoods[distances < self._threshold] = self._pmfObservationsWhenClose[observation]

		# ...and a different one if it's outside it
		likelihoods[distances>=self._threshold] = self._pmfObservationsWhenFar[observation]

		return likelihoods


class RSSsensor(Sensor):

	def __init__(
			self, position, transmitter_power=1, path_loss_exponent=2, noise_variance=1, minimum_amount_of_power=1e-5,
			pseudo_random_numbers_generator=np.random.RandomState()):

		super().__init__(position, pseudo_random_numbers_generator)

		# the power of the transmitter
		self._txPower = transmitter_power

		# the path loss exponent (depending on the medium)
		self._pathLossExponent = path_loss_exponent

		# the variance of the additive noise in the model (it is meant to be accessed from outside)
		self.noiseVar = noise_variance

		# ...and, for the sake of efficiency, the standard deviation
		self._noiseStd = np.sqrt(noise_variance)

		# minimum amount of power the sensor is able to measure
		self._minimumPower = minimum_amount_of_power

	def likelihoodMean(self, distances):

		return 10*np.log10(self._txPower/distances**self._pathLossExponent + self._minimumPower)

	def detect(self, target_pos):

		distance = np.linalg.norm((self.position - target_pos))

		return self.likelihoodMean(distance) + self.measurement_noise()

	def measurement_noise(self):

		return self._pseudo_random_numbers_generator.randn()*self._noiseStd

	def likelihood(self, observation, positions):

		# the distances to ALL the positions are computed
		distances = np.linalg.norm(np.subtract(positions,self.position),axis=0)

		return scipy.stats.norm.pdf(observation, self.likelihoodMean(distances), self._noiseStd)
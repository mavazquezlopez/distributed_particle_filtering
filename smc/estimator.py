import abc

import numpy as np
import numpy.linalg

import state


def geometric_median(points, max_iterations=100, tolerance=0.001):

	# initial estimate
	estimate = np.median(points, axis=1)

	for i in range(max_iterations):

		# the norms for the vectors joining the previous estimate with every point
		norms = numpy.linalg.norm(np.subtract(points, estimate[:, np.newaxis]), axis=0)

		# is any of the norms is zero?
		is_zero = np.isclose(norms, 0.0)

		# if one of the norms is zero (there should be one at most)
		if np.any(is_zero):

			# we find out its position...
			i_zero_norm, = np.where(is_zero)

			# ...and the estimate of the median is the corresponding point
			estimate = points[:, i_zero_norm[0]]

			return estimate

		# this is used a couple of times below
		invnorms = 1.0 / norms

		# a new estimate according to the Weiszfeld algorithm
		new_estimate = np.multiply(points, invnorms[np.newaxis, :]).sum(axis=1)/invnorms.sum()

		# if the new estimate is close enough to the old one...
		if numpy.linalg.norm(new_estimate-estimate) < tolerance:

			# ...it gets a pass
			return new_estimate

		# ...otherwise, the new estimate becomes will be used in the next iteration
		estimate = new_estimate

	return estimate


class Estimator:

	def __init__(self, DPF, i_PE=0):

		self.DPF = DPF
		self.i_PE = i_PE

	# by default, it is assumed no communication is required
	def messages(self, PEs_topology):

		return 0

	def estimate(self):

		return


class Delegating(Estimator):

	def estimate(self):

		return self.DPF.compute_mean()


class Mean(Estimator):

	def estimate(self):

		# the means from all the PEs are stacked (horizontally) in a single array
		jointMeans = np.hstack([PE.compute_mean() for PE in self.DPF._PEs])

		return jointMeans.mean(axis=1)[:, np.newaxis]

	def messages(self, PEs_topology):

		# the distances (in hops) between each pair of PEs
		distances = PEs_topology.distances_between_PEs()

		return distances[self.i_PE, :].sum()*state.n_elements_position


class WeightedMean(Mean):

	def estimate(self):

		aggregated_weights = self.DPF.aggregated_weights

		# the aggregated weights are not necessarily normalized
		normalized_aggregated_weights = aggregated_weights/aggregated_weights.sum()

		# notice that "compute_mean" will return a numpy array the size of the state (rather than a scalar)
		return np.multiply(
			np.hstack([PE.compute_mean() for PE in self.DPF._PEs]),
			normalized_aggregated_weights).sum(axis=1)[:, np.newaxis]


class Mposterior(Estimator):

	def combine_posterior_distributions(self, posteriors):

		# the Mposterior algorithm is used to obtain a a new distribution
		joint_particles, joint_weights = self.DPF.Mposterior(posteriors)

		return np.multiply(joint_particles, joint_weights).sum(axis=1)[np.newaxis].T

	def estimate(self):

		# the (FULL) distributions computed by all the PEs are gathered in a list of tuples (samples and weights)
		posteriors = [(PE.get_state().T,np.exp(PE.log_weights)) for PE in self.DPF._PEs]

		return self.combine_posterior_distributions(posteriors)

	def messages(self, PEs_topology):

		# the distances (in hops) between each pair of PEs
		distances = PEs_topology.distances_between_PEs()

		# TODO: this assumes all PEs have the same number of particles: that of the self.i_PE-th one
		return distances[self.i_PE,:].sum()*self.DPF._PEs[self.i_PE].n_particles*state.n_elements_position


class PartialMposterior(Mposterior):

	def __init__(self, DPF, n_particles, i_PE=0):

		super().__init__(DPF, i_PE)

		self.n_particles = n_particles

	def estimate(self):

		# a number of samples is drawn from the distribution of each PE (all equally weighted) to build a list of tuples
		# (samples and weights)
		posteriors = [(PE.get_samples_at(
			self.DPF._resamplingAlgorithm.getIndexes(np.exp(PE.log_weights), self.n_particles)
		).T, np.full(self.n_particles, 1.0/self.n_particles)) for PE in self.DPF._PEs]

		return self.combine_posterior_distributions(posteriors)

	def messages(self, PEs_topology):

		# the distances (in hops) between each pair of PEs
		distances = PEs_topology.distances_between_PEs()

		return distances[self.i_PE,:].sum()*self.n_particles*state.n_elements_position


class GeometricMedian(Estimator):

	def __init__(self, DPF, i_PE=0, max_iterations=100, tolerance=0.001):

		super().__init__(DPF, i_PE)

		self._maxIterations = max_iterations
		self._tolerance = tolerance

	def estimate(self):

		# the first (0) sample of each PE is collected
		samples = np.hstack([PE.get_samples_at([0]) for PE in self.DPF._PEs])

		return geometric_median(samples,max_iterations=self._maxIterations,tolerance=self._tolerance)[:,np.newaxis]

	def messages(self, PEs_topology):

		# the distances (in hops) between each pair of PEs
		distances = PEs_topology.distances_between_PEs()

		return distances[self.i_PE,:].sum()*state.n_elements_position


class StochasticGeometricMedian(GeometricMedian):

	def __init__(self, DPF, n_particles, i_PE=0, max_iterations=100, tolerance=0.001):

		super().__init__(DPF, i_PE, max_iterations, tolerance)

		self.n_particles = n_particles

	def estimate(self):

		# a number of samples is drawn from the distribution of each PE (all equally weighted)
		# to build a list of tuples (samples and weights)
		samples = np.hstack(
			[PE.get_samples_at(self.DPF._resamplingAlgorithm.getIndexes(np.exp(PE.log_weights),
			self.n_particles)) for PE in self.DPF._PEs])

		return geometric_median(samples,max_iterations=self._maxIterations,tolerance=self._tolerance)[:,np.newaxis]

	def messages(self, PEs_topology):

		return super().messages(PEs_topology)*self.n_particles


class SinglePEMean(Estimator):

	def estimate(self):

		return self.DPF._PEs[self.i_PE].compute_mean()


class SinglePEGeometricMedian(Estimator):

	def __init__(self, DPF, iPE, max_iterations=100, tolerance=0.001):

		super().__init__(DPF, iPE)

		self._maxIterations = max_iterations
		self._tolerance = tolerance

	def estimate(self):

		return geometric_median(
			self.DPF._PEs[self.i_PE].samples, max_iterations=self._maxIterations, tolerance=self._tolerance
		)[:, np.newaxis]


class SinglePEGeometricMedianWithinRadius(SinglePEGeometricMedian):

	def __init__(self, DPF, iPE, PEs_topology, radius, max_iterations=100, tolerance=0.001):

		super().__init__(DPF, iPE, max_iterations, tolerance)

		self._distances = PEs_topology.distances_between_PEs()

		# the indexes of the PEs that are at most "radius" hops from the selected PE
		self._i_relevant_PEs, = np.where((self._distances[self.i_PE] > 0) & (self._distances[self.i_PE]<=radius))

		# the selected PE is also included
		self._i_relevant_PEs = np.append(self._i_relevant_PEs, self.i_PE)

	def estimate(self):

		# one sample from each of the above PEs
		samples = np.vstack([self.DPF._PEs[iPE].get_samples_at(0) for iPE in self._i_relevant_PEs]).T

		return geometric_median(samples, max_iterations=self._maxIterations, tolerance=self._tolerance)[:,np.newaxis]
	
	def messages(self, PEs_topology):
		"""
		:return: the number of messages exchanged between PEs due to a call to "estimate"
		"""

		# the number of hops for each neighbour times the number of floats sent per message
		return self._distances[self.i_PE, self._i_relevant_PEs].sum()*state.n_elements_position
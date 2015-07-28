import numpy as np
import math
import abc

import state
import smc.estimator
import smc.mposterior.share

# this is required (due to a bug?) for import rpy2
import readline

import rpy2.robjects as robjects

# in order to load an R package
from rpy2.robjects.packages import importr

# for automatic conversion from numpy arrays to R data types
import rpy2.robjects.numpy2ri
rpy2.robjects.numpy2ri.activate()

class ParticleFilter(metaclass=abc.ABCMeta):
	
	def __init__(self,nParticles,resamplingAlgorithm,resamplingCriterion):
		
		self._nParticles = nParticles
		
		self._resamplingAlgorithm = resamplingAlgorithm
		self._resamplingCriterion = resamplingCriterion
	
	@abc.abstractmethod
	def initialize(self):

		pass
	
	@abc.abstractmethod
	def step(self,observations):
		
		pass
	
	@abc.abstractmethod
	def getState(self):
		
		pass

# =========================================================================================================

class CentralizedTargetTrackingParticleFilter(ParticleFilter):
	
	def __init__(self,nParticles,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,aggregatedWeight=1.0):
		
		super().__init__(nParticles,resamplingAlgorithm,resamplingCriterion)
		
		# a vector with the weights is created...but not initialized (that must be done by the "initialize" method)
		self._logWeights = np.empty(nParticles)
		
		# the state equation is encoded in the transition kernel
		self._stateTransitionKernel = stateTransitionKernel
		
		# the prior is needed to inialize the state
		self._prior = prior
		
		# the sensors are kept
		self._sensors = sensors
		
		# this variable just keeps tabs on the sum of all the weights
		self._aggregatedWeight = aggregatedWeight
	
	def initialize(self):
		
		# initial samples...
		self._state = self._prior.sample(self._nParticles)
		
		# the weights are assigned equal probabilities
		self._logWeights.fill(np.log(self._aggregatedWeight)-np.log(self._nParticles))
		
	def step(self,observations):
		
		assert len(observations) == len(self._sensors)
		
		# every particle is updated (previous state is not stored...)
		self._state = np.hstack(
			[self._stateTransitionKernel.nextState(self._state[:,i:i+1]) for i in range(self._nParticles)])
		
		# TODO: this may cause a "divide by zero" warning when a likelihood is very small
		# for each sensor, we compute the likelihood of EVERY particle (position)
		loglikelihoods = np.log(np.array([sensor.likelihood(obs,state.position(self._state)) for sensor,obs in zip(self._sensors,observations)]))
		
		# for each particle, we compute the product of the likelihoods for all the sensors
		loglikelihoodsProduct = loglikelihoods.sum(axis=0)
		
		# the weights are updated
		self._logWeights += loglikelihoodsProduct
		
		# the aggregated weight is kept up to date at all times
		self.updateAggregatedWeight()
		
		# whatever is required (it depends on the algorithm) to avoid weights degeneracy...
		self.avoidWeightDegeneracy()

	def getState(self):
		
		return self._state

	def resample(self,normalizedLogWeights):
		
		# the weights need to be converted to "natural" units
		normalizedWeights = np.exp(normalizedLogWeights)
		
		# we check whether a resampling step is actually needed or not
		if self._resamplingCriterion.isResamplingNeeded(normalizedWeights):
			
			try:
				# the resampling algorithm is used to decide which particles to keep
				iParticlesToBeKept = self._resamplingAlgorithm.getIndexes(normalizedWeights)
				
			except ValueError:
				
				# this should mean the normalized weights don't add up EXACTLY to one...we renormalize them...
				normalizedWeights /= normalizedWeights.sum()
				
				# ...and try again
				iParticlesToBeKept = self._resamplingAlgorithm.getIndexes(normalizedWeights)
				
			# the above indexes are used to update the state
			self._state = self._state[:,iParticlesToBeKept]
			
			# note that if the weights have been normalized ("standard" centralized particle filter), then "self._aggregatedWeight" is equal to 1
			self._logWeights.fill(np.log(self._aggregatedWeight)-np.log(self._nParticles))
		
	def getParticle(self,index):
		
		return (self._state[:,index:index+1].copy(),self._logWeights[index])
	
	def getSamplesAt(self,indexes):
		
		"""Obtain (just) the samples at certain given indexes.
		
		This yields a "view" of the data, rather than a copy.
		
		Parameters
		----------
		indexes: 1-D ndarray
			The indexes of the requested particles
			
		Returns
		-------
		samples: 2-D ndarray
			The selected samples
		"""
		
		return self._state[:,indexes]
	
	@property
	def samples(self):
		
		return self._state
	
	@samples.setter
	def samples(self,value):
		
		if value.shape==self._state.shape:
			
			self._state = value
			
		else:
			
			raise Exception('the number and/or dimensions of the samples are not equal to the current ones')
	
	def setParticle(self,index,particle):
		
		self._state[:,index:index+1] = particle[0]
		self._logWeights[index] = particle[1]
		
		# the sum of the weights might have changed...
		self.updateAggregatedWeight()

	def updateAggregatedWeight(self):
		
		# the aggregated weight is simply the sum of the non-normalized weights
		self._aggregatedWeight = np.exp(self._logWeights).sum()

	def computeMean(self):
		
		# if all the weights in this PF/PE are zero...
		if self._aggregatedWeight==0:
			
			# ...then an all-zeros estimate is returned...though any should do since this estimate must contribute zero
			return np.zeros((state.nElements,1))
		
		normalizedLogWeights = self._logWeights - np.log(self._aggregatedWeight)

		# element-wise multiplication of the state vectors and their correspondent weights...followed by addition => weighted mean
		return np.multiply(self._state,np.exp(normalizedLogWeights)).sum(axis=1)[np.newaxis].T

	# this methods encapsulates the parts within the code of "step" which are different in this class and its children
	def avoidWeightDegeneracy(self):
		
		# if all the weights are zero...
		if self._aggregatedWeight==0:
			
			# ...then normalization makes no sense and we just initialize the weights again
			self._logWeights.fill(-np.log(self._nParticles))

		else:
		
			self._logWeights -= np.log(self._aggregatedWeight)
			
		# we forced this above
		self._aggregatedWeight = 1.0
		
		# the normalized weights are used to resample
		self.resample(self._logWeights)
	
	@property
	def logWeights(self):
		
		return self._logWeights
	
	@logWeights.setter
	def logWeights(self,value):
		
		if self._logWeights.shape==value.shape:
			
			self._logWeights=value
			
		else:
			
			raise Exception('the number of weights does not match the number of particles')
			
# =========================================================================================================

class EmbeddedTargetTrackingParticleFilter(CentralizedTargetTrackingParticleFilter):
	
	def getAggregatedWeight(self):
		
		return self._aggregatedWeight
	
	def divideWeights(self,factor):
		
		self._logWeights -= np.log(factor)
		self._aggregatedWeight /= factor

	def avoidWeightDegeneracy(self):
		
		# if all the weights are zero...
		if self._aggregatedWeight==0:
			
			# ...there is nothing we can do
			return
		
		else:
			# the normalized weights are used to resample
			self.resample(self._logWeights - np.log(self._aggregatedWeight))

# =========================================================================================================

class DistributedTargetTrackingParticleFilter(ParticleFilter):
	
	def __init__(self,nPEs,nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,
			  PFsClass=CentralizedTargetTrackingParticleFilter,PFsInitialAggregatedWeight=1.0):
		
		super().__init__(nPEs*nParticlesPerPE,resamplingAlgorithm,resamplingCriterion)
		
		# it is handy to keep the number of PEs in a variable
		self._nPEs = nPEs
		
		# a list of lists, the first one containing the indices of the sensors "seen" by the first PE...and so on
		self._PEsSensorsConnections = PEsSensorsConnections

		# number of particles per Pe
		self._nParticlesPerPE = nParticlesPerPE
		
		# the particle filters are built (each one associated with a different set of sensors)
		self._PEs = [PFsClass(nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,
													[s for iSensor,s in enumerate(sensors) if iSensor in connections],
													aggregatedWeight=PFsInitialAggregatedWeight) for connections in  PEsSensorsConnections]

	def initialize(self):
		
		# all the PFs are initialized
		for PE in self._PEs:
			
			PE.initialize()

		# we keep track of the elapsed (discreet) time instants
		self._n = 0

	def step(self,observations):
		
		# a step is taken in every PF (ideally, this would occur concurrently)
		for iPe,PE in enumerate(self._PEs):
			
			# only the appropriate observations are passed to this PE
			# NOTE: it is assumed that the order in which the observations are passed is the same as that of the sensors when building the PF
			PE.step(observations[self._PEsSensorsConnections[iPe]])
			
		# a new time instant has elapsed
		self._n += 1
	
	def getState(self):
		
		# the state from every PE is gathered together
		return np.hstack([PE.getState() for PE in self._PEs])
	
	def nMessages(self):
		
		return 0

# =========================================================================================================

#class LikelihoodConsensusDistributedTargetTrackingParticleFilter(DistributedTargetTrackingParticleFilter):
	
	#def __init__(self,nPEs,nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,
			  #PFsClass=CentralizedTargetTrackingParticleFilter,PFsInitialAggregatedWeight=1.0):
		
		#super().__init__(nPEs,nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections)
	
	#def polynomialApproximation(self,x,y,degree):
		
		#import itertools
		#import scipy.misc
		##import numpy.linalg
		
		## for the sake of conveninience when following the pseudocode in "Likelihood Consensus and its Application to Distributed Particle Filtering":
		
		## the size of the state
		#M = state.nElements
		
		## the chosen degreen for the polynomial approximation
		#R_p = degree
		#R_d = degree
		
		## theoretical number of monomials in the approximation
		#R_a = scipy.misc.comb(R_p + M,R_p,exact=True)
		
		##monomialsExponents = list(itertools.filterfalse(lambda x: sum(x)>R_p, itertools.product(range(R_p+1),repeat=M)))
		
		## an iterator with the exponents of each variable in every monomial
		#monomialsExponents = itertools.filterfalse(lambda x: sum(x)>R_p, itertools.product(range(R_p+1),repeat=M))
		
		
		#exponentsMatrix = np.array(list(itertools.filterfalse(lambda x: sum(x)>R_p, itertools.product(range(R_p+1),repeat=M))))
		
		## -----------
		#q = 2
		
		#np.random.seed(123412341)
		
		#x = np.random.randn(M,20)
		#true_phi = (x.T[:,:,np.newaxis]**exponentsMatrix.T[np.newaxis,:,:]).prod(axis=1)
		
		#alphas = np.random.randn(q,R_a)
		#gammas = np.random.randn(R_a)
		
		#y = []
		#d = []
		
		#for sample in true_phi:
			
			#y.append((sample[np.newaxis,:]*alphas).sum(axis=1))
			#d.append(sample.dot(gammas))
			
		
		#A = np.vstack(y)
		##A = A + np.random.randn(*A.shape)*0.1
		
		#d = np.array(d)
		
		##np.allclose(true_phi.dot(alphas.T),A)
		##np.linalg.cond(true_phi.T.dot(true_phi))
		
		##sol = np.dot(np.dot(np.linalg.inv(np.dot(true_phi.T,true_phi)),true_phi.T),A)
		#sol = np.linalg.pinv(true_phi).dot(A)
		
		#gammaHat = np.linalg.pinv(true_phi).dot(d)
		
		##true_phi.T
		
		## -----------
		
		## the number of points used in the approximation
		#J = x.shape[1]
		
		##phi2 = np.empty((J,R_a))
		
		### for every sample used to compute the approximation
		##for iSample,sample in enumerate(x.T):
			
			###print('================ wap ================')
			
			### each "tuple" of exponents represents a monomial
			###for iExponents,exponents in enumerate(monomialsExponents):
			##for iExponents,exponents in enumerate(exponentsMatrix):
			
				##phi2[iSample,iExponents] = prod(sample**exponents)
				###print('iSample = {}'.format(iSample))
				###print('iExponents = {}'.format(iExponents))
				###print('result = {}'.format(sample**exponents))
				
		
		## in the first matrix, we just replicate the samples matrix (<number of sample>,<component within sample>) along the third dimension;
		## in the second matrix, the third dimension gives the number of monomial
		#phi = (x.T[:,:,np.newaxis]**exponentsMatrix.T[np.newaxis,:,:]).prod(axis=1)
		
		
		#import code
		#code.interact(local=dict(globals(), **locals()))

# =========================================================================================================

class TargetTrackingParticleFilterWithDRNA(DistributedTargetTrackingParticleFilter):
	
	def __init__(self,exchangePeriod,exchangeRecipe,aggregatedWeightsUpperBound,nParticlesPerPE,normalizationPeriod,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,
			  PFsClass=EmbeddedTargetTrackingParticleFilter):
		
		super().__init__(exchangeRecipe.getNumberOfPEs(),nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,
				   PFsClass=PFsClass,PFsInitialAggregatedWeight=1.0/exchangeRecipe.getNumberOfPEs())
		
		# a exchange of particles among PEs will happen every...
		self._exchangePeriod = exchangePeriod
		
		self._exchangeRecipe = exchangeRecipe

		# period for the normalization of the aggregated weights
		self._normalizationPeriod = normalizationPeriod
		
		# we get a unique exchange map from this network
		self._exchangeMap,_ = exchangeRecipe.getExchangeTuples()
		
		self._estimator = smc.estimator.WeightedMean(self)
		
		# the number of hops to get a message from one node of the network to another
		self._nAverageHopsOnTransmission = 1

	def step(self,observations):
		
		super().step(observations)
		
		# if it is exchanging particles time
		if (self._n % self._exchangePeriod == 0):
			
			#self.exchangeParticles()
			self._exchangeRecipe.performExchange(self)
			
			# after the exchange, the aggregated weight of every PE must be updated
			for PE in self._PEs:
				
				PE.updateAggregatedWeight()
		
		# needed to perform the normalization below
		aggregatedWeightsSum = self.getAggregatedWeights().sum()
		
		# if every aggregated weight is zero...
		if np.isclose(aggregatedWeightsSum,0):
			
			# ...we reinitialize the weights for all the particles of all the PEs
			self.resetWeights()
			
			# ...and skip the normalization code below
			return
		
		# the aggregated weights must be normalized every now and then to avoid computer precision issues
		if self._n % self._normalizationPeriod == 0:
			
			# ...to scale all the weights within ALL the PEs
			for PE in self._PEs:
				
				PE.divideWeights(aggregatedWeightsSum)
	
	def getAggregatedWeights(self):
		
		return np.array([PE.getAggregatedWeight() for PE in self._PEs])

	def resetWeights(self):
		
		"""It sets every weight of every PE to the same value.
		"""
		
		# every PE will be assigned the same aggregated weight:
		aggregatedWeight = 1.0/self._nPEs
		
		# for every PE in this DPF...
		for PE in self._PEs:
			
			# the aggregated weight is set...
			PE._aggregatedWeight = aggregatedWeight
			
			# ...along with the individual weights within the PE
			PE.logWeights = np.full(PE._nParticles,-np.log(self._nPEs)-np.log(PE._nParticles))

	def computeMean(self):
		
		return self._estimator.estimate()
	
	def nMessages(self):
		
		# each sensor must send its observation to every PE, and each transmission entails a certain number of "hops" on average
		return len(self._sensors)*self._nPEs*self._nAverageHopsOnTransmission

# =========================================================================================================

class DistributedTargetTrackingParticleFilterWithMposterior(DistributedTargetTrackingParticleFilter):
	
	def __init__(self,exchangeRecipe,nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,findWeiszfeldMedianParameters,sharingPeriod,
			  exchangeManager,PFsClass=CentralizedTargetTrackingParticleFilter):
		
		super().__init__(exchangeRecipe.getNumberOfPEs(),nParticlesPerPE,resamplingAlgorithm,resamplingCriterion,prior,stateTransitionKernel,sensors,PEsSensorsConnections,PFsClass=PFsClass)
		
		self._sharingPeriod = sharingPeriod
		self._nSharedParticles = exchangeRecipe.nParticlesExchangedBetweenTwoNeighbours
		self._exchangeRecipe = exchangeRecipe
		
		# the (R) Mposterior package is imported...
		self._Mposterior = importr('Mposterior')
		
		# ...and the parameters to be passed to the required function are kept
		self._findWeiszfeldMedianParameters = findWeiszfeldMedianParameters
		
		# we get a unique exchange map from this network
		self._exchangeMap,self._neighboursWithParticles = exchangeRecipe.getExchangeTuples()
		
		# this object is responsible for the sharing step
		self._exchangeManager = exchangeManager

	def Mposterior(self,posteriorDistributions):
		
		"""Applies the Mposterior algorithm to weight the samples of a list of "subset posterior distribution"s.
		
		Parameters
		----------
		posteriorDistributions: list of tuples
			A list in which each element is a tuple representing a "subset posterior distribution": the first element are the samples, and the second the associated weights
		
		Returns
		-------
		samples: tuple
			The first element is a 2-D ndarray with all the samples, and the second the corresponding weights.
		"""
		
		# the samples of all the "subset posterior distribution"s are extracted
		samples = [posterior[0] for posterior in posteriorDistributions]
		
		# R function implementing the "M posterior" algorithm is called
		weiszfeldMedian = self._Mposterior.findWeiszfeldMedian(samples,**self._findWeiszfeldMedianParameters)

		# the weights assigned by the algorithm to each "subset posterior distribution"
		weiszfeldWeights = np.array(weiszfeldMedian[1])
		
		# a numpy array containing all the particles (coming from all the PEs)
		jointParticles = np.array(weiszfeldMedian[3]).T
		
		# the weight of each PE is scaled according to the "weiszfeldWeights" and, all of them are stacked together
		jointWeights =	np.hstack([posterior[1]*weight for posterior,weight in zip(posteriorDistributions,weiszfeldWeights)])
		
		return (jointParticles,jointWeights)

	def step(self,observations):
		
		super().step(observations)
		
		# if it is sharing particles time
		if (self._n % self._sharingPeriod == 0):
			
			self._exchangeManager.share(self)
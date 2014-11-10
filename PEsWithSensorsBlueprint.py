import abc
import networkx

class PEsWithSensorsBlueprint(metaclass=abc.ABCMeta):
	
	def __init__(self,nSensors,parameters=None):
		
		self._nSensors = nSensors
		self._parameters = parameters
	
	@abc.abstractmethod
	def getPEsSensorsConnections(self,nPEs):
		
		return

class FullyConnected(PEsWithSensorsBlueprint):
	
	def getPEsSensorsConnections(self,nPEs):
		
		return [list(range(self._nSensors))]*nPEs

class FixedNumberOfPesPerSensor(PEsWithSensorsBlueprint):
	
	def getPEsSensorsConnections(self,nPEs):

		# each sensor is associated with "nPEsPerSensor" PEs
		sensorsDegrees = [self._parameters['number of PEs per sensor']]*self._nSensors
		
		# how many (at least) sensors should be connected to every PE
		nSensorsPerPE = (self._parameters['number of PEs per sensor']*self._nSensors) // nPEs
		
		# each PE should is connected to the the number of sensors specified in the corresponding position of this list
		PEsDegrees = [nSensorsPerPE]*nPEs
		
		# if some connections remain in order to satisfy that each sensor is connected to the given number of PEs per sensor
		for iPE in range(self._parameters['number of PEs per sensor']*self._nSensors % nPEs):
			PEsDegrees[iPE] +=  1
	
		# a bipartite graph with one set of nodes given by the sensors and other by the PEs
		graph = networkx.bipartite_havel_hakimi_graph(sensorsDegrees,PEsDegrees)
	
		return [graph.neighbors(iPE+self._nSensors) for iPE in range(nPEs)]
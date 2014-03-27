import numpy as np
import matplotlib
import matplotlib.pyplot as plt

class Painter:
	def __init__(self,sensorsPositions):
		self._figure = plt.figure('room')
		self._ax = plt.axes()
		self._sensorsPositions = sensorsPositions
		
		self._previousPosition = None
		
		# so that the program doesn't wait for the open windows to be closed in order to continue
		plt.ion()
		
	def go(self):
		self._ax.plot(self._sensorsPositions[:,0], self._sensorsPositions[:,1], '+')
		self._ax.set_aspect('equal', 'datalim')
		plt.show()
		#plt.hold(True)
		
	def update(self,position):
		
		#import code
		#code.interact(local=dict(globals(), **locals()))
		
		#plt.hold(False)
		#self.go()
		plt.hold(True)
		
		# if this is not the first update (i.e., there exists a previous position)...
		if self._previousPosition is not None:
			# ...plot the step taken
			self._ax.plot(np.array([self._previousPosition[0],position[0]]),np.array([self._previousPosition[1],position[1]]),'r-')
		# if this is the first update...
		else:
			# ...just plot the position
			self._ax.plot(position[0],position[1],'r*')
		
		plt.draw()
		
		self._previousPosition = position
		
class PainterDecorator(Painter):
	def __init__(self,decorated):
		# let the superclass do its stuff
		super().__init__(decorated._sensorsPositions)
		
		# we keep a reference to the object being decorated
		self._decorated = decorated
		
class WithBorder(PainterDecorator):
	def __init__(self,decorated,roomBottomLeftCorner,roomTopRightCorner):
		super().__init__(decorated)
		self._roomBottomLeftCorner = roomBottomLeftCorner
		self._roomTopRightCorner = roomTopRightCorner
		self._roomDiagonalVector = self._roomTopRightCorner - self._roomBottomLeftCorner
		
	def go(self):
		# let the superclass do its stuff
		super().go()
		
		# we define a rectangular patch...
		roomEdge = matplotlib.patches.Rectangle((self._roomBottomLeftCorner[0],self._roomBottomLeftCorner[1]), self._roomDiagonalVector[0], self._roomDiagonalVector[1], fill=False, color='blue')
		
		# ...and added to the axes
		self._ax.add_patch(roomEdge)
		
		
''' 
This module defines the commonly used radial basis functions (RBFs) 
shown in the below table. For each RBF expression,
:math:`r = ||x - c||_2` and :math:`\epsilon` is a shape parameter.
:math:`x` and :math:`c` are the evaluation points and RBF centers, 
respectively. RBFs which are not defined in this module can be created 
with the *RBF* class.

=================================  ============  ======================================
Name                               Abbreviation  Expression
=================================  ============  ======================================
Eighth-order polyharmonic spline   phs8          :math:`(\epsilon r)^8\log(\epsilon r)`
Seventh-order polyharmonic spline  phs7          :math:`(\epsilon r)^7`
Sixth-order polyharmonic spline    phs6          :math:`(\epsilon r)^6\log(\epsilon r)`
Fifth-order polyharmonic spline    phs5          :math:`(\epsilon r)^5`
Fourth-order polyharmonic spline   phs4          :math:`(\epsilon r)^4\log(\epsilon r)`
Third-order polyharmonic spline    phs3          :math:`(\epsilon r)^3`
Second-order polyharmonic spline   phs2          :math:`(\epsilon r)^2\log(\epsilon r)`
First-order polyharmonic spline    phs1          :math:`\epsilon r`
Multiquadratic                     mq            :math:`(1 + (\epsilon r)^2)^{1/2}`
Inverse multiquadratic             imq           :math:`(1 + (\epsilon r)^2)^{-1/2}`
Inverse quadratic                  iq            :math:`(1 + (\epsilon r)^2)^{-1}`
Gaussian                           ga            :math:`\exp(-(\epsilon r)^2)`
Exponential                        exp           :math:`\exp(-(\epsilon r))`
=================================  ============  ======================================

''' 
from __future__ import division 
import sympy 
from sympy.utilities.autowrap import ufuncify 
import numpy as np 
import copy
import warnings

# define global symbolic variables
_R = sympy.symbols('R')
_EPS = sympy.symbols('EPS')


def _replace_nan(x):
  ''' 
  this is orders of magnitude faster than np.nan_to_num
  '''
  x[np.isnan(x)] = 0.0
  return x


def _check_lambdified_output(fin):
  ''' 
  when lambdifying a sympy expression, the output is a scalar if the 
  expression is independent of R. This function checks the output of a 
  lambdified function and if the output is a scalar then it expands 
  the output to the proper output size. The proper output size is 
  (N,M) where N is the number of collocation points and M is the 
  number of basis functions
  '''
  def fout(*args,**kwargs):
    out = fin(*args,**kwargs)
    x = args[0]
    eps = args[-1]
    if np.isscalar(out):
      arr = np.empty((x.shape[0],eps.shape[0]),dtype=float)
      arr[...] = out
      out = arr

    return out

  return fout  


def get_R():
  ''' 
  returns the symbolic variable for :math:`r` which is used to 
  instantiate an *RBF*
  '''
  return copy.deepcopy(_R)


def get_EPS():
  ''' 
  returns the symbolic variable for :math:`\epsilon` which is used to 
  instantiate an *RBF*
  '''
  return copy.deepcopy(_EPS)


class RBF(object):
  ''' 
  Stores a symbolic expression of a Radial Basis Function (RBF) and 
  evaluates the expression numerically when called. 
  
  Parameters
  ----------
  expr : sympy expression
    Symbolic expression of the RBF. This must be a function of the 
    symbolic variable *R*, which is returned by the function *get_R*. 
    *R* is the radial distance to the RBF center.  The expression may 
    optionally be a function of *EPS*, which is a shape parameter 
    obtained by the function *get_EPS*.  If *EPS* is not provided then 
    *R* is substituted with *R* * *EPS*.
  
  package : string, optional  
    Controls how the symbolic expressions are converted into numerical 
    functions. This can be either 'numpy' or 'cython'. If 'numpy' then 
    the symbolic expression is converted using *sympy.lambdify*. If 
    'cython' then the expression if converted using 
    *sympy.utilities.autowrap.ufuncify*, which converts the expression 
    to cython code and then compiles it. Note that there is a ~1 
    second overhead to compile the cython code.
  
  tol : float, optional  
    If an evaluation point, *x*, is within *tol* of an RBF center, 
    *c*, then *x* is considered equal to *c*. The returned value is 
    then the RBF at the symbolically evaluated limit as *x*->*c*. This 
    is only useful when there is a removable singularity at *c*, such 
    as for polyharmonic splines. If *tol* is not provided then there 
    will be no special treatment for when *x* is close to *c*. Note 
    that computing the limit as *x*->*c* can be very time intensive.
  
  Examples
  --------
  Instantiate an inverse quadratic RBF

  >>> R = get_R()
  >>> EPS = get_EPS()
  >>> iq_expr = 1/(1 + (EPS*R)**2)
  >>> iq = RBF(iq_expr)
  
  Evaluate an inverse quadratic at 10 points ranging from -5 to 5. 
  Note that the evaluation points and centers are two dimensional 
  arrays

  >>> x = np.linspace(-5.0,5.0,10)[:,None]
  >>> center = np.array([[0.0]])
  >>> values = iq(x,center)
    
  '''
  def __init__(self,expr,package='cython',tol=None):    
    if not expr.has(_R):
      raise ValueError('RBF expression must be a function of rbf.basis.R')
    
    if not expr.has(_EPS):
      # if EPS is not in the expression then substitute EPS*R for R
      expr = expr.subs(_R,_EPS*_R)
      
    self._expr = expr
    self.set_package(package)
    self.set_tol(tol)
    self.clear_cache()

  def __call__(self,x,c,eps=None,diff=None):
    ''' 
    Evaluates the RBF
    
    Parameters                                       
    ----------                                         
    x : (N,D) array 
      evaluation points
                                                                       
    c : (M,D) array 
      RBF centers 
        
    eps : (M,) array, optional
      shape parameters for each RBF. Defaults to 1.0
                                                                           
    diff : (D,) int array, optional
      Tuple indicating the derivative order for each spatial 
      dimension. For example, if there are three spatial dimensions 
      then providing (2,0,1) would return the RBF after 
      differentiating it twice along the first axis and once along the 
      third axis.

    Returns
    -------
    out : (N,M) array
      Returns the RBFs with centers *c* evaluated at *x*

    Notes
    -----
    This function evaluates the RBF and its derivatives symbolically 
    using sympy and then the symbolic expression is converted to a 
    numerical function. The numerical function is cached and then 
    reused when this function is called again with the same derivative 
    specification.

    All NaNs are replaced with zeros and divide by zero warnings are 
    suppressed. This is an ad-hoc, but fast, way to handle the 
    removable singularity with polyharmonic splines, and it does not 
    require symbolically calculating the limit at the singularity. 
    This is not guaranteed to produce the correct result at the 
    singularity, and one may prefer to handle the singularity 
    separately by setting a value for *tol*.
    '''
    x = np.asarray(x,dtype=float)
    c = np.asarray(c,dtype=float)
    if eps is None:
      eps = np.ones(c.shape[0],dtype=float)   
    else:  
      eps = np.asarray(eps,dtype=float)

    if diff is None:
      diff = (0,)*x.shape[1]
    else:
      # make sure diff is immutable
      diff = tuple(diff)

    # make sure the input arguments have the proper dimensions
    if not ((x.ndim == 2) & (c.ndim == 2)):
      raise ValueError(
        '*x* and *c* must be two-dimensional arrays')

    if not (x.shape[1] == c.shape[1]):
      raise ValueError(
        '*x* and *c* must have the same number of spatial dimensions')

    if not ((eps.ndim == 1) & (eps.shape[0] == c.shape[0])):
      raise ValueError(
        '*eps* must be a one-dimensional array with length equal to '
        'the number of rows in *c*')
    
    if not (len(diff) == x.shape[1]):
      raise ValueError(
        '*diff* must have the same length as the number of spatial '
        'dimensions in *x* and *c*')

    # expand to allow for broadcasting
    x = x[:,None,:]
    c = c[None,:,:]
    # this does the same thing as np.rollaxis(x,-1) but is much faster
    x = np.einsum('ijk->kij',x)
    c = np.einsum('ijk->kij',c)
    # add function to cache if not already
    if diff not in self._cache:
      self.add_to_cache(diff)
 
    args = (tuple(x)+tuple(c)+(eps,))    
    # ignore divide by zero warnings and then replace nans with zeros. 
    # This is an ad-hoc (but fast!) way of handling the removable 
    # singularity in polyharmonic splines. A more appropriate way to 
    # handle the singularity is by specifying *tol*.
    with warnings.catch_warnings():
      warnings.simplefilter("ignore")
      out = self._cache[diff](*args)
      out = _replace_nan(out)

    return out

  def set_tol(self,tol):
    self._tol = tol
    
  def set_package(self,package):
    if package in ['cython','numpy']:
      self._package = package
    else:
      raise ValueError('package must either be "cython" or "numpy" ')  
  
  def add_to_cache(self,diff):
    '''     
    Symbolically evaluates the specified derivative and then compiles 
    it to a function which can be evaluated numerically. The numerical 
    function is cached for later use. It is not necessary to use this 
    method directly because it is called as needed by the *__call__* 
    method.
    
    Parameters
    ----------
    diff : (D,) int array
      Derivative specification
        
    '''   
    diff = tuple(diff)
    dim = len(diff)
    c_sym = sympy.symbols('c:%s' % dim)
    x_sym = sympy.symbols('x:%s' % dim)    
    r_sym = sympy.sqrt(sum((xi-ci)**2 for xi,ci in zip(x_sym,c_sym)))
    # differentiate the RBF 
    expr = self._expr.subs(_R,r_sym)            
    for xi,order in zip(x_sym,diff):
      if order == 0:
        continue
      expr = expr.diff(*(xi,)*order)

    if self._tol is not None:
      # find the limit of the differentiated expression as x->c. This 
      # is necessary for polyharmonic splines, which have removable 
      # singularities. NOTE: this finds the limit from only one 
      # direction and the limit may change when using a different 
      # direction.
      center_expr = expr
      for xi,ci in zip(x_sym,c_sym):
        center_expr = center_expr.limit(xi,ci)

      # create a piecewise symbolic function which is center_expr when 
      # _R<tol and expr otherwise
      expr = sympy.Piecewise((center_expr,r_sym<self._tol),
                             (expr,True)) 
      
    if self._package == 'numpy':
      func = sympy.lambdify(x_sym+c_sym+(_EPS,),expr,'numpy')
      func = _check_lambdified_output(func)
      self._cache[diff] = func

    elif self._package == 'cython':        
      func = ufuncify(x_sym+c_sym+(_EPS,),expr)
      self._cache[diff] = func
    
  def clear_cache(self):
    ''' 
    Deletes entries stored in the cache.
    '''
    self._cache = {}
        

# Instantiate some common RBFs
phs8 = RBF((_EPS*_R)**8*sympy.log(_EPS*_R),package='cython')
phs6 = RBF((_EPS*_R)**6*sympy.log(_EPS*_R),package='cython')
phs4 = RBF((_EPS*_R)**4*sympy.log(_EPS*_R),package='cython')
phs2 = RBF((_EPS*_R)**2*sympy.log(_EPS*_R),package='cython')
phs7 = RBF((_EPS*_R)**7,package='cython')
phs5 = RBF((_EPS*_R)**5,package='cython')
phs3 = RBF((_EPS*_R)**3,package='cython')
phs1 = RBF(_EPS*_R,package='cython')
exp = RBF(sympy.exp(-(_EPS*_R)),package='cython')
imq = RBF(1/sympy.sqrt(1+(_EPS*_R)**2),package='cython')
iq = RBF(1/(1+(_EPS*_R)**2),package='cython')
ga = RBF(sympy.exp(-(_EPS*_R)**2),package='cython')
mq = RBF(sympy.sqrt(1 + (_EPS*_R)**2),package='cython')



"""Exact conditional covariance for independent native input pixels.

The operator reproduces order-1 constant-zero interpolation and the production
motion-mask support normalization. It is not a model of instrument covariance.
"""
import numpy as np
from scipy.sparse import csr_matrix

def bilinear_operator(x,y,good,variance):
    x=np.asarray(x,float);y=np.asarray(y,float);good=np.asarray(good);variance=np.asarray(variance,float)
    if x.shape!=y.shape or x.ndim!=2 or good.ndim!=2 or good.dtype.kind!='b'or variance.shape!=good.shape or not np.isfinite(x).all()or not np.isfinite(y).all():raise ValueError('Invalid coordinate/mask dimensions')
    if not np.isfinite(variance[good]).all()or np.any(variance[good]<=0):raise ValueError('Good native pixels require finite positive calibrated variance')
    h,w=good.shape;support=np.zeros(x.size);weights=[];indices=[];rows=[]
    for row,(xx,yy)in enumerate(zip(x.ravel(),y.ravel())):
        # scipy mode=constant returns cval for an entirely outside coordinate;
        # it does not interpolate the partial inside edge as grid-constant does.
        if not(0<=xx<=w-1 and 0<=yy<=h-1):continue
        ix=int(np.floor(xx));iy=int(np.floor(yy));dx=xx-ix;dy=yy-iy;entries=[]
        for px,py,weight in [(ix,iy,(1-dx)*(1-dy)),(ix+1,iy,dx*(1-dy)),(ix,iy+1,(1-dx)*dy),(ix+1,iy+1,dx*dy)]:
            if weight>0 and 0<=px<w and 0<=py<h and good[py,px]:entries.append((py*w+px,weight))
        support[row]=sum(weight for _,weight in entries)
        if support[row]>=.995:
            for index,weight in entries:rows.append(row);indices.append(index);weights.append(weight/support[row])
    operator=csr_matrix((weights,(rows,indices)),shape=(x.size,good.size))
    native_variance=np.where(good,variance,0.).ravel()
    diagonal=np.asarray(operator.power(2)@native_variance).ravel()
    linear=np.asarray(operator@native_variance).ravel()
    return dict(operator=operator,support=support.reshape(x.shape),usable=(support>=.995).reshape(x.shape),
                native_variance=native_variance,variance_diagonal=diagonal.reshape(x.shape),linear_interpolated_variance=linear.reshape(x.shape))

def covariance_for_rows(operator,variance,rows):
    subset=operator[np.asarray(rows,dtype=int)]
    return (subset.multiply(np.asarray(variance).reshape(1,-1))@subset.T).toarray()

def affine_amplitude_weights(template,covariance):
    template=np.asarray(template,float);covariance=np.asarray(covariance,float)
    if template.ndim!=1 or len(template)<3 or covariance.shape!=(len(template),len(template))or not np.isfinite(template).all()or not np.isfinite(covariance).all():raise ValueError('Insufficient/invalid affine patch')
    diagonal=np.diag(covariance)
    if np.any(diagonal<=0):raise ValueError('Affine patch requires positive variance')
    design=np.column_stack([template,np.ones(len(template))]);weighted=design/np.sqrt(diagonal[:,None])
    if np.linalg.matrix_rank(weighted)!=2:raise ValueError('Affine patch design is rank deficient')
    fisher=design.T@(design/diagonal[:,None]);inverse=np.linalg.inv(fisher)
    coefficients=inverse@(design.T/diagonal);amplitude=coefficients[0]
    exact=float(amplitude@covariance@amplitude);naive=float(inverse[0,0])
    if not np.isfinite([exact,naive]).all()or min(exact,naive)<=0:raise ValueError('Affine uncertainty invalid')
    return dict(amplitude_weights=amplitude,background_weights=coefficients[1],variance_exact=exact,variance_diagonal_assumption=naive,
                sigma_ratio_exact_to_diagonal=float(np.sqrt(exact/naive)),amplitude_constant_response=float(amplitude.sum()),
                amplitude_template_response=float(amplitude@template),fisher_condition_number=float(np.linalg.cond(fisher)))

"""PNG evidence from actual registered pixels and fitted trajectories.

Small moving/stationary stacks adapt Ivan's motion review algorithm (2b6dc43).
They are visual checks, never calibrated significance or flux measurements.
"""
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates


def stretch(array, floor, ceiling):
    span=max(float(ceiling-floor),1e-12)
    finite=np.isfinite(array)
    levels=np.clip((np.where(finite,array,floor)-floor)/span,0,1)
    pixels=np.rint(10+241*np.arcsinh(levels*5)/np.arcsinh(5)).astype(np.uint8)
    return np.where(finite,pixels,0).astype(np.uint8)


def write_png(directory, name, pixels):
    path=Path(directory)/name
    Image.fromarray(pixels).save(path,format='PNG',optimize=False)
    size=path.stat().st_size
    if size>1024*1024:
        from .contracts import InferenceError
        raise InferenceError('output_limit','An evidence resource exceeds the supported size')
    return {'name':name,'media_type':'image/png','size_bytes':size}


def fitted_positions(track,times):
    measured=np.asarray(track.positions_xy)
    selected=times[list(track.epochs)]
    delta=selected-selected.mean()
    velocity=delta@measured/(delta@delta)
    return measured.mean(axis=0)+(times-selected.mean())[:,None]*velocity


def stack_evidence(evidence,coordinates,radius=14):
    dy,dx=np.meshgrid(np.arange(-radius,radius+1),np.arange(-radius,radius+1),indexing='ij')
    total=np.zeros(dx.shape); count=np.zeros(dx.shape,dtype=int)
    for image,(x,y) in zip(evidence,coordinates):
        finite=np.isfinite(image); points=[y+dy,x+dx]
        value=map_coordinates(np.where(finite,image,0),points,order=1,mode='constant',cval=0)
        covered=map_coordinates(finite.astype(float),points,order=1,mode='constant',cval=0)>=.995
        total+=np.where(covered,value,0); count+=covered
    return np.divide(total,np.sqrt(count),where=count>0,out=np.full(total.shape,np.nan))


def track_images(track,times,evidence,*,bloom=False):
    epochs=list(track.epochs); fitted=fitted_positions(track,times)[epochs]
    moving=stack_evidence(evidence[epochs],fitted)
    stationary=stack_evidence(evidence[epochs],np.broadcast_to(np.median(fitted,axis=0),fitted.shape))
    values=np.concatenate([moving[np.isfinite(moving)],stationary[np.isfinite(stationary)]])
    floor=0 if bloom else 2
    ceiling=np.sqrt(len(epochs)) if bloom else max(6,float(np.percentile(values,99.8))) if values.size else 6
    return stretch(moving,floor,ceiling),stretch(stationary,floor,ceiling)

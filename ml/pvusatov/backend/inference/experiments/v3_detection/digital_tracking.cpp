// Development-only streaming linear template search. No velocity cube or truth input.
#include <cmath>
#include <cstdint>
#include <algorithm>
extern "C" int search(const float* maps,const double* times,int n,int h,int w,
 double vmin,double vmax,double step,int displacement,double sigma,double threshold,
 int64_t work_cap,int robust,float* best,int16_t* bx,int16_t* by,int64_t* work_out){
 int64_t work=0;const double span=times[n-1]-times[0];
 std::fill(best,best+h*w,-INFINITY);
 for(int dy=-displacement;dy<=displacement;dy++)for(int dx=-displacement;dx<=displacement;dx++){
  double vx=dx*step/span,vy=dy*step/span,speed=std::hypot(vx,vy);
  if(speed<vmin||speed>vmax||std::hypot(dx*step,dy*step)<1.5)continue;
  int ox[32],oy[32];int xmin=0,xmax=w,ymin=0,ymax=h;
  for(int k=0;k<n;k++){
   ox[k]=(int)std::round(vx*(times[k]-times[0]));oy[k]=(int)std::round(vy*(times[k]-times[0]));
   xmin=std::max(xmin,-ox[k]);xmax=std::min(xmax,w-ox[k]);ymin=std::max(ymin,-oy[k]);ymax=std::min(ymax,h-oy[k]);
  }
  if(xmin>=xmax||ymin>=ymax)continue;
  double correlation=0;
  for(int a=0;a<n;a++)for(int b=0;b<n;b++){
   double ddx=ox[a]-ox[b],ddy=oy[a]-oy[b];correlation+=std::exp(-(ddx*ddx+ddy*ddy)/(4*sigma*sigma));
  }
  double norm=n-correlation/n;if(norm<.05)continue;norm=std::sqrt(norm);
  work+=(int64_t)(xmax-xmin)*(ymax-ymin)*n;
  if(work>work_cap){*work_out=work;return 1;}
  for(int y=ymin;y<ymax;y++)for(int x=xmin;x<xmax;x++){
   float sum=0,positive=0,largest=0,second=0,third=0;bool valid=true;
   for(int k=0;k<n;k++){float z=maps[(k*h+y+oy[k])*w+x+ox[k]];if(!std::isfinite(z)){valid=false;break;}sum+=z;positive+=std::max(0.f,z);if(z>=largest){third=second;second=largest;largest=z;}else if(z>=second){third=second;second=z;}else if(z>third){third=z;}}
   if(!valid||(robust&&third<1.2))continue;float score=robust?(positive-largest)/std::sqrt(n-1.):sum/norm;
   if(score>=threshold&&score>best[y*w+x]){best[y*w+x]=score;bx[y*w+x]=dx;by[y*w+x]=dy;}
  }
 }
 *work_out=work;return 0;
}

// Separate DEVELOPMENT single-epoch competitor; copied bounded search from joint_tracking.cpp.
// NEW development-only typed trajectory search, informed by the preserved v3
// prototype. Float64 accumulation; portable flags, no fast-math/velocity cube.
#include <algorithm>
#include <cmath>
#include <cstdint>

static bool hypothesis(const double* t,int n,int reference_n,int h,int w,
 double vmin,double vmax,double step,int dx,int dy,double sigma,
 int* ox,int* oy,int& xmin,int& xmax,int& ymin,int& ymax,double& norm){
 const double span=t[n-1]-t[0],vx=dx*step/span,vy=dy*step/span;
 const double speed=std::hypot(vx,vy);
 if(speed<vmin||speed>vmax||std::hypot(dx*step,dy*step)<1.5)return false;
 xmin=0;xmax=w;ymin=0;ymax=h;
 for(int k=0;k<n;k++){
  ox[k]=(int)std::round(vx*(t[k]-t[0]));oy[k]=(int)std::round(vy*(t[k]-t[0]));
  xmin=std::max(xmin,-ox[k]);xmax=std::min(xmax,w-ox[k]);
  ymin=std::max(ymin,-oy[k]);ymax=std::min(ymax,h-oy[k]);
 }
 if(xmin>=xmax||ymin>=ymax)return false;
 double correlation=0.;
 for(int a=0;a<n;a++)for(int b=0;b<n;b++){
  const double x=ox[a]-ox[b],y=oy[a]-oy[b];
  correlation+=std::exp(-(x*x+y*y)/(4*sigma*sigma));
 }
 // Template is active only in selected epochs; constant nuisance uses ALL
 // reference epochs, not incorrectly the selected subset count.
 norm=n-correlation/reference_n;
 if(norm<.05)return false;
 norm=std::sqrt(norm);return true;
}

extern "C" int64_t plan(const double* t,int n,int reference_n,int h,int w,
 double vmin,double vmax,double step,int d,double sigma,int64_t* anchors,int64_t* velocities){
 int64_t total=0,tests=0,hypotheses=0;
 for(int dy=-d;dy<=d;dy++)for(int dx=-d;dx<=d;dx++){
  int ox[32],oy[32],xmin,xmax,ymin,ymax;double norm;
  if(!hypothesis(t,n,reference_n,h,w,vmin,vmax,step,dx,dy,sigma,ox,oy,xmin,xmax,ymin,ymax,norm))continue;
  const int64_t area=(int64_t)(xmax-xmin)*(ymax-ymin);
  tests+=area;total+=area*n;hypotheses++;
 }
 *anchors=tests;*velocities=hypotheses;return total;
}

extern "C" int search(const float* maps,const double* t,int n,int reference_n,int h,int w,
 double vmin,double vmax,double step,int d,double sigma,double threshold,int64_t cap,int robust,
 float* best,int16_t* bx,int16_t* by,int64_t* work_out,int64_t* valid_out,int64_t* qualified_out){
 int64_t work=0,valid_count=0,qualified=0;
 std::fill(best,best+h*w,-INFINITY);
 for(int dy=-d;dy<=d;dy++)for(int dx=-d;dx<=d;dx++){
  int ox[32],oy[32],xmin,xmax,ymin,ymax;double norm;
  if(!hypothesis(t,n,reference_n,h,w,vmin,vmax,step,dx,dy,sigma,ox,oy,xmin,xmax,ymin,ymax,norm))continue;
  work+=(int64_t)(xmax-xmin)*(ymax-ymin)*n;
  if(work>cap){*work_out=work;*valid_out=valid_count;*qualified_out=qualified;return 1;}
  for(int y=ymin;y<ymax;y++)for(int x=xmin;x<xmax;x++){
   double sum=0.,positive=0.,largest=0.,second=0.,third=0.;bool valid=true;
   for(int k=0;k<n;k++){
    const float value=maps[(k*h+y+oy[k])*w+x+ox[k]];
    if(!std::isfinite(value)){valid=false;break;}
    const double z=value;sum+=z;positive+=std::max(0.,z);
    if(z>=largest){third=second;second=largest;largest=z;}
    else if(z>=second){third=second;second=z;}else if(z>third)third=z;
   }
   if(!valid)continue;valid_count++;
   qualified++;
   // Compare positive coherent moving-template evidence against the best
   // single-epoch point impulse under the SAME static projection. C_jj is
   // 1-1/reference_n; C*1 is the moving template's sampled mean response.
   // Equal independent epoch noise/Gaussian PSF approximation ONLY.
   const double moving=std::max(0.,sum/norm);
   const double transient=largest/std::sqrt(1.-1./reference_n);
   const double score=std::sqrt(std::max(0.,moving*moving-transient*transient));
   // Keep the unconditional maximum for null/look-elsewhere diagnostics.
   // Python applies the preregistered proposal threshold after the search.
   if(score>best[y*w+x]){best[y*w+x]=(float)score;bx[y*w+x]=dx;by[y*w+x]=dy;}
  }
 }
 *work_out=work;*valid_out=valid_count;*qualified_out=qualified;return 0;
}

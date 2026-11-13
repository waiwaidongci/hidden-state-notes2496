import {request,post} from './client';export const comparisonApi={comparisons:()=>request('/comparisons'),create:(data:any)=>post('/comparisons',data)};

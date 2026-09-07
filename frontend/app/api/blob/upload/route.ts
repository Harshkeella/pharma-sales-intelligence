import {handleUpload, type HandleUploadBody} from '@vercel/blob/client';

export async function POST(request:Request){
  try{
    const body=await request.json() as HandleUploadBody;
    return Response.json(await handleUpload({
      request,body,
      onBeforeGenerateToken:async pathname=>{
        if(!/^sessions\/[a-f0-9]{64}\/uploads\/[^/]+\.xlsx$/i.test(pathname))throw new Error('Invalid upload path.');
        return {allowedContentTypes:['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],maximumSizeInBytes:100_000_000,addRandomSuffix:true};
      },
      onUploadCompleted:async()=>{}
    }));
  }catch(error:any){return Response.json({error:error.message||'Upload could not be authorized.'},{status:400})}
}

/** Read PNG/JPEG dimensions without decoding pixels or relying on a visible canvas. */
export function imageSize(base64,format) {
  const raw=atob(base64);
  const u8=i=>raw.charCodeAt(i),u16=i=>(u8(i)<<8)|u8(i+1),u32=i=>(u8(i)*16777216)+(u8(i+1)<<16)+(u8(i+2)<<8)+u8(i+3);
  if(format==='png'&&raw.length>=24&&raw.slice(1,4)==='PNG')return {width:u32(16),height:u32(20)};
  if(format==='jpeg'&&u8(0)===255&&u8(1)===216){
    let i=2;while(i+4<raw.length){
      if(u8(i)!==255)break;while(u8(i)===255)i++;
      const marker=u8(i++);if(marker===217||marker===218)break;
      if(marker===1||(marker>=208&&marker<=215))continue;
      const length=u16(i);if(length<2||i+length>raw.length)break;
      if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker)&&length>=7)return {height:u16(i+3),width:u16(i+5)};
      i+=length;
    }
  }
  throw new Error('Cannot read screenshot pixel dimensions.');
}

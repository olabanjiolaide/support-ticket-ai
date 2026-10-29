// Offsets are Unicode code points, matching Python, rather than UTF-16 units.
export function editEvidence(document, operation, index, offset=null) {
  const copy=structuredClone(document),parts=copy.parts,part=parts[index];
  if(!part)throw new Error('Choose a fragment first.');
  const source=Array.from(copy.source_text);
  let edited;
  if(operation==='split'){
    if(!Number.isInteger(offset) || offset<=part.start || offset>=part.end)throw new Error('Place the cursor inside the selected fragment.');
    const left=source.slice(part.start,offset).join(''),right=source.slice(offset,part.end).join('');
    if(!left.trim() || !right.trim())throw new Error('Both new fragments must contain text.');
    if(parts.length>=24)throw new Error('At most 24 evidence fragments are supported.');
    edited=[part.id];
    parts.splice(index,1,{...part,end:offset,text:left},{...part,start:offset,text:right});
  } else if(operation==='merge'){
    const next=parts[index+1];
    if(!next)throw new Error('Choose a fragment that has a following fragment.');
    edited=[part.id,next.id];
    parts.splice(index,2,{...part,end:next.end,text:source.slice(part.start,next.end).join('')});
  } else throw new Error('Unknown evidence edit.');
  // Interpretations of changed text must be reviewed again. Unchanged evidence retains its choices.
  const ids=new Map();
  parts.forEach((item,i)=>{
    const previous=item.id;item.id=`part-${i+1}`;
    if(edited.includes(previous)){item.role='unconfirmed';item.group_id=null;item.category=null;}
    else ids.set(previous,item.id);
  });
  // Do not silently invent relationships for newly split or merged evidence.
  copy.relations=(copy.relations || []).filter(relation=>relation.evidence_parts.every(id=>!edited.includes(id)))
    .map(relation=>({...relation,evidence_parts:relation.evidence_parts.map(id=>ids.get(id))}));
  copy.schema_version=document.schema_version>=3?3:2;
  return copy;
}

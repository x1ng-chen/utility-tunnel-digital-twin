<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomComponent } from 'echarts/components';
use([CanvasRenderer,LineChart,GridComponent,TooltipComponent,LegendComponent,MarkLineComponent,DataZoomComponent]);
const props=withDefaults(defineProps<{ labels:string[]; series:Array<{name:string;data:number[];color?:string}>; threshold?:number; compact?:boolean; zoom?:boolean; theme?:'dark'|'light' }>(),{threshold:undefined,compact:false,zoom:false,theme:'light'});
const palette=computed(()=>props.theme==='light'
  ? {line:'#c5d5e8',muted:'#53657b',grid:'rgba(148,172,202,.24)',background:'#ffffff',text:'#1c3049',signal:'#1766c3',area:'rgba(23,102,195,.08)',threshold:'#915200'}
  : {line:'#334155',muted:'#8da0b8',grid:'rgba(51,65,85,.32)',background:'#09111d',text:'#e5edf7',signal:'#38bdf8',area:'rgba(56,189,248,.10)',threshold:'#f59e0b'});
const option=computed(()=>({animationDuration:420,backgroundColor:'transparent',color:props.series.map((s)=>s.color||palette.value.signal),tooltip:{trigger:'axis',backgroundColor:palette.value.background,borderColor:palette.value.line,textStyle:{color:palette.value.text,fontFamily:'Cascadia Mono',fontSize:12}},legend:{show:props.series.length>1,textStyle:{color:palette.value.muted,fontFamily:'Cascadia Mono'}},grid:{left:46,right:22,top:props.series.length>1?42:20,bottom:props.zoom?52:34},xAxis:{type:'category',data:props.labels,boundaryGap:false,axisLine:{lineStyle:{color:palette.value.line}},axisLabel:{color:palette.value.muted,fontSize:10},splitLine:{show:true,lineStyle:{color:palette.value.grid}}},yAxis:{type:'value',scale:true,axisLine:{show:true,lineStyle:{color:palette.value.line}},axisLabel:{color:palette.value.muted,fontSize:10},splitLine:{lineStyle:{color:palette.value.grid}}},dataZoom:props.zoom?[{type:'inside'},{type:'slider',height:16,bottom:8,borderColor:palette.value.line,backgroundColor:palette.value.background,fillerColor:'rgba(56,189,248,.18)'}]:[],series:props.series.map((s)=>({name:s.name,type:'line',data:s.data,smooth:.25,showSymbol:false,lineStyle:{width:2,color:s.color||palette.value.signal},areaStyle:{color:palette.value.area},markLine:props.threshold==null?undefined:{silent:true,symbol:'none',label:{formatter:'阈值 {c}',color:palette.value.threshold},lineStyle:{color:palette.value.threshold,type:'dashed'},data:[{yAxis:props.threshold}]}}))}));
</script>
<template><VChart :class="['ops-chart',{compact}]" :option="option" autoresize /></template>

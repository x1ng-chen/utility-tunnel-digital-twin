<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, RadarChart, GaugeChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, DataZoomComponent, RadarComponent } from 'echarts/components';
use([CanvasRenderer,LineChart,RadarChart,GaugeChart,GridComponent,TooltipComponent,LegendComponent,MarkLineComponent,DataZoomComponent,RadarComponent]);
const props=withDefaults(defineProps<{ labels:string[]; series:Array<{name:string;data:number[];color?:string}>; threshold?:number; compact?:boolean; zoom?:boolean }>(),{threshold:undefined,compact:false,zoom:false});
const option=computed(()=>({animationDuration:420,backgroundColor:'transparent',color:props.series.map((s)=>s.color||'#38bdf8'),tooltip:{trigger:'axis',backgroundColor:'#09111d',borderColor:'#334155',textStyle:{color:'#e5edf7',fontFamily:'Cascadia Mono',fontSize:12}},legend:{show:props.series.length>1,textStyle:{color:'#8da0b8',fontFamily:'Cascadia Mono'}},grid:{left:46,right:22,top:props.series.length>1?42:20,bottom:props.zoom?52:34},xAxis:{type:'category',data:props.labels,boundaryGap:false,axisLine:{lineStyle:{color:'#334155'}},axisLabel:{color:'#8da0b8',fontSize:10},splitLine:{show:true,lineStyle:{color:'rgba(51,65,85,.32)'}}},yAxis:{type:'value',scale:true,axisLine:{show:true,lineStyle:{color:'#334155'}},axisLabel:{color:'#8da0b8',fontSize:10},splitLine:{lineStyle:{color:'rgba(51,65,85,.42)'}}},dataZoom:props.zoom?[{type:'inside'},{type:'slider',height:16,bottom:8,borderColor:'#334155',backgroundColor:'#09111d',fillerColor:'rgba(56,189,248,.18)'}]:[],series:props.series.map((s)=>({name:s.name,type:'line',data:s.data,smooth:.25,showSymbol:false,lineStyle:{width:2,color:s.color||'#38bdf8'},areaStyle:{color:'rgba(56,189,248,.10)'},markLine:props.threshold==null?undefined:{silent:true,symbol:'none',label:{formatter:'阈值 {c}',color:'#f59e0b'},lineStyle:{color:'#f59e0b',type:'dashed'},data:[{yAxis:props.threshold}]}}))}));
</script>
<template><VChart :class="['ops-chart',{compact}]" :option="option" autoresize /></template>

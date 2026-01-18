'use client';

export default function SkeletonCard({ height = 'h-32', width = 'w-full', className = '' }) {
  return (
    <div 
      className={`${height} ${width} bg-gray-700 rounded-xl animate-pulse ${className}`}
    />
  );
}

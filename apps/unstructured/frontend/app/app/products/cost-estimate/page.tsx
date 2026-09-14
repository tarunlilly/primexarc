
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import AppLayout from '@/components/layout/AppLayout'
import { CostEstimation } from '@/components/CostEstimation'

export default function CostEstimatePage() {
  const navigate = useNavigate()

  return (
    <AppLayout>
      <div className="p-6">
        {/* Breadcrumb Navigation */}
        <div className="flex items-center mb-6">
          <Link to="/app/products" className="flex items-center text-sm text-gray-500 hover:text-gray-700 transition-colors">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Products
          </Link>
          <span className="mx-2 text-gray-400">/</span>
          <span className="text-sm font-medium text-gray-900">Cost Estimation</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Cost Estimation</h1>
          <p className="text-gray-600 mt-1">
            Estimate the cost of creating AI-ready data from your files before running the full pipeline.
          </p>
        </div>

        {/* Cost Estimation Component */}
        <CostEstimation />
      </div>
    </AppLayout>
  )
}





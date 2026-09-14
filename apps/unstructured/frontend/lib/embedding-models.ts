/**
 * Embedding model configuration for frontend.
 * 
 * This module provides utilities for working with embedding models,
 * including getting available options, dimensions, and API key requirements.
 * Models are fetched from the backend API - backend is the single source of truth.
 */

import { apiClient } from './api-client'

export interface EmbeddingModelOption {
  value: string
  label: string
}

export interface EmbeddingModel {
  id: string
  name: string
  description: string
  dimension: number
  requires_api_key: boolean
  cost_per_token?: number
  metadata?: Record<string, any>
}

// Cache for embedding models fetched from API
let embeddingModelsCache: EmbeddingModel[] | null = null
let embeddingModelsCacheTime: number = 0
const CACHE_DURATION = 5 * 60 * 1000 // 5 minutes

/**
 * Fetch embedding models from the API.
 * Backend is the single source of truth - no fallback models.
 * 
 * @param useCache - Whether to use cached models if available
 * @returns Array of embedding models from backend
 * @throws Error if API call fails
 */
async function fetchEmbeddingModels(useCache: boolean = true): Promise<EmbeddingModel[]> {
  // Check cache first
  if (useCache && embeddingModelsCache && (Date.now() - embeddingModelsCacheTime) < CACHE_DURATION) {
    return embeddingModelsCache
  }

  try {
    const response = await apiClient.getEmbeddingModels({ free_only: false })
    
    if (response.error || !response.data) {
      const errorMessage = response.error || 'Failed to fetch embedding models from API'
      console.error('Failed to fetch embedding models from API:', errorMessage)
      // Clear cache on error to force fresh fetch next time
      embeddingModelsCache = null
      throw new Error(errorMessage)
    }

    // Cache the results
    embeddingModelsCache = response.data.models || []
    embeddingModelsCacheTime = Date.now()
    
    return embeddingModelsCache || []
  } catch (error) {
    console.error('Error fetching embedding models:', error)
    // Clear cache on error to force fresh fetch next time
    embeddingModelsCache = null
    throw error
  }
}

/**
 * Get list of embedding model options for select dropdowns.
 * 
 * @param useCache - Whether to use cached models if available
 * @returns Array of embedding model options with value and label
 */
export async function getEmbeddingModelOptions(useCache: boolean = true): Promise<EmbeddingModelOption[]> {
  try {
    const models = await fetchEmbeddingModels(useCache)
    return models.map((model) => ({
      value: model.id,
      label: model.name
    }))
  } catch (error) {
    console.error('Failed to get embedding model options:', error)
    // Return empty array if API fails - UI should handle this gracefully
    return []
  }
}

/**
 * Synchronous version that uses cache only.
 * Returns empty array if cache not available - backend is required.
 */
export function getEmbeddingModelOptionsSync(): EmbeddingModelOption[] {
  if (embeddingModelsCache) {
    return embeddingModelsCache.map((model) => ({
      value: model.id,
      label: model.name
    }))
  }
  
  // No fallback - return empty array if cache not available
  return []
}

/**
 * Get the embedding dimension for a given model name.
 * 
 * @param modelName - The embedding model identifier
 * @returns The dimension of the embedding model, or undefined if model not found
 */
export async function getEmbeddingDimension(modelName: string): Promise<number | undefined> {
  // Check cache first
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find(m => m.id === modelName)
    if (model) return model.dimension
  }
  
  // Try to fetch from API
  try {
    const models = await fetchEmbeddingModels(false)
    const model = models.find(m => m.id === modelName)
    if (model) return model.dimension
  } catch (error) {
    console.error('Error fetching embedding dimension:', error)
  }
  
  // Return undefined if model not found
  return undefined
}

/**
 * Synchronous version that uses cache only.
 */
export function getEmbeddingDimensionSync(modelName: string): number | undefined {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find(m => m.id === modelName)
    if (model) return model.dimension
  }
  
  // No fallback - return undefined if not in cache
  return undefined
}

/**
 * Check if an embedding model requires an API key.
 * 
 * @param modelName - The embedding model identifier
 * @returns True if the model requires an API key, false otherwise
 */
export async function requiresApiKey(modelName: string): Promise<boolean> {
  // Check cache first
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find(m => m.id === modelName)
    if (model) return model.requires_api_key
  }
  
  // Try to fetch from API
  try {
    const models = await fetchEmbeddingModels(false)
    const model = models.find(m => m.id === modelName)
    if (model) return model.requires_api_key || false
  } catch (error) {
    console.error('Error checking API key requirement:', error)
  }
  
  // Return false if model not found
  return false
}

/**
 * Synchronous version that uses cache only.
 */
export function requiresApiKeySync(modelName: string): boolean {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find(m => m.id === modelName)
    if (model) return model.requires_api_key
  }
  
  // No fallback - return false if not in cache
  return false
}

/**
 * Format embedding model name for display.
 * 
 * @param modelName - The embedding model identifier
 * @returns Formatted display name for the model
 */
export function formatEmbeddingModelName(modelName: string): string {
  if (embeddingModelsCache) {
    const model = embeddingModelsCache.find(m => m.id === modelName)
    if (model) return model.name
  }
  
  // No fallback - return model ID if not in cache
  return modelName
}

/**
 * Preload embedding models from API (call this on app initialization).
 * This ensures models are available immediately when needed.
 */
export async function preloadEmbeddingModels(): Promise<void> {
  try {
    await fetchEmbeddingModels(false)
  } catch (error) {
    console.error('Failed to preload embedding models:', error)
  }
}


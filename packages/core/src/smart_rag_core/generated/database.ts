export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  app: {
    Tables: {
      admin_notifications: {
        Row: {
          acknowledged_at: string | null
          acknowledged_by: string | null
          body: string
          created_at: string
          id: string
          metadata: Json
          notification_kind: string
          severity: string
          title: string
        }
        Insert: {
          acknowledged_at?: string | null
          acknowledged_by?: string | null
          body: string
          created_at?: string
          id?: string
          metadata?: Json
          notification_kind: string
          severity?: string
          title: string
        }
        Update: {
          acknowledged_at?: string | null
          acknowledged_by?: string | null
          body?: string
          created_at?: string
          id?: string
          metadata?: Json
          notification_kind?: string
          severity?: string
          title?: string
        }
        Relationships: []
      }
      allowed_email_domains: {
        Row: {
          created_at: string
          domain: string
          id: string
        }
        Insert: {
          created_at?: string
          domain: string
          id?: string
        }
        Update: {
          created_at?: string
          domain?: string
          id?: string
        }
        Relationships: []
      }
      audit_chain_anchors: {
        Row: {
          anchor_date: string
          anchored_at: string
          chain_hash: string
          event_count: number
          export_uri: string | null
          id: string
        }
        Insert: {
          anchor_date: string
          anchored_at?: string
          chain_hash: string
          event_count: number
          export_uri?: string | null
          id?: string
        }
        Update: {
          anchor_date?: string
          anchored_at?: string
          chain_hash?: string
          event_count?: number
          export_uri?: string | null
          id?: string
        }
        Relationships: []
      }
      audit_events: {
        Row: {
          actor_role: Database["app"]["Enums"]["user_role"] | null
          actor_user_id: string | null
          authorization_version: number | null
          chain_seq: number | null
          created_at: string
          event_hash: string | null
          event_type: string
          id: string
          payload: Json
          previous_hash: string | null
          purpose: string | null
          resource_id: string | null
          resource_type: string | null
          session_id: string | null
          target_id: string | null
          target_type: string | null
          visibility_generation: number | null
        }
        Insert: {
          actor_role?: Database["app"]["Enums"]["user_role"] | null
          actor_user_id?: string | null
          authorization_version?: number | null
          chain_seq?: number | null
          created_at?: string
          event_hash?: string | null
          event_type: string
          id?: string
          payload?: Json
          previous_hash?: string | null
          purpose?: string | null
          resource_id?: string | null
          resource_type?: string | null
          session_id?: string | null
          target_id?: string | null
          target_type?: string | null
          visibility_generation?: number | null
        }
        Update: {
          actor_role?: Database["app"]["Enums"]["user_role"] | null
          actor_user_id?: string | null
          authorization_version?: number | null
          chain_seq?: number | null
          created_at?: string
          event_hash?: string | null
          event_type?: string
          id?: string
          payload?: Json
          previous_hash?: string | null
          purpose?: string | null
          resource_id?: string | null
          resource_type?: string | null
          session_id?: string | null
          target_id?: string | null
          target_type?: string | null
          visibility_generation?: number | null
        }
        Relationships: []
      }
      bm25_index_jobs: {
        Row: {
          attempt_count: number
          chunk_id: string | null
          created_at: string
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          operation: Database["app"]["Enums"]["bm25_job_operation"]
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }
        Insert: {
          attempt_count?: number
          chunk_id?: string | null
          created_at?: string
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          operation: Database["app"]["Enums"]["bm25_job_operation"]
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Update: {
          attempt_count?: number
          chunk_id?: string | null
          created_at?: string
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key?: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          operation?: Database["app"]["Enums"]["bm25_job_operation"]
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "bm25_index_jobs_chunk_id_fkey"
            columns: ["chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "bm25_index_jobs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      bm25_index_versions: {
        Row: {
          activated_at: string | null
          created_at: string
          id: string
          index_schema_version: string
          is_active: boolean
          normalization_version: string
          version_number: number
        }
        Insert: {
          activated_at?: string | null
          created_at?: string
          id?: string
          index_schema_version?: string
          is_active?: boolean
          normalization_version?: string
          version_number: number
        }
        Update: {
          activated_at?: string | null
          created_at?: string
          id?: string
          index_schema_version?: string
          is_active?: boolean
          normalization_version?: string
          version_number?: number
        }
        Relationships: []
      }
      budget_reservations: {
        Row: {
          amount_usd: number
          committed_at: string | null
          created_at: string
          expires_at: string
          id: string
          released_at: string | null
          reservation_kind: string
          run_id: string | null
          status: Database["app"]["Enums"]["budget_reservation_status"]
          updated_at: string
          user_id: string | null
        }
        Insert: {
          amount_usd: number
          committed_at?: string | null
          created_at?: string
          expires_at: string
          id?: string
          released_at?: string | null
          reservation_kind: string
          run_id?: string | null
          status?: Database["app"]["Enums"]["budget_reservation_status"]
          updated_at?: string
          user_id?: string | null
        }
        Update: {
          amount_usd?: number
          committed_at?: string | null
          created_at?: string
          expires_at?: string
          id?: string
          released_at?: string | null
          reservation_kind?: string
          run_id?: string | null
          status?: Database["app"]["Enums"]["budget_reservation_status"]
          updated_at?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "budget_reservations_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      citations: {
        Row: {
          chunk_id: string | null
          citation_index: number
          created_at: string
          id: string
          message_id: string | null
          provenance: Json
          run_id: string
          snippet: string | null
        }
        Insert: {
          chunk_id?: string | null
          citation_index: number
          created_at?: string
          id?: string
          message_id?: string | null
          provenance?: Json
          run_id: string
          snippet?: string | null
        }
        Update: {
          chunk_id?: string | null
          citation_index?: number
          created_at?: string
          id?: string
          message_id?: string | null
          provenance?: Json
          run_id?: string
          snippet?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "citations_chunk_id_fkey"
            columns: ["chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "citations_message_id_fkey"
            columns: ["message_id"]
            isOneToOne: false
            referencedRelation: "messages"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "citations_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      company_settings: {
        Row: {
          authorization_version: number
          company_name: string | null
          created_at: string
          daily_graph_index_budget_usd: number
          daily_ingestion_budget_usd: number | null
          default_document_visibility: Database["app"]["Enums"]["document_visibility"]
          graph_bulk_approved_at: string | null
          graph_bulk_window_ends_at: string | null
          graph_bulk_window_starts_at: string | null
          id: string
          legal_hold_enabled: boolean
          monthly_graph_maintenance_budget_usd: number
          monthly_llm_budget_usd: number | null
          quarantine_byte_cap: number | null
          quarantine_ttl_hours: number
          retention_days: number
          timezone: string
          updated_at: string
          upload_quota_bytes: number | null
          visibility_generation: number
        }
        Insert: {
          authorization_version?: number
          company_name?: string | null
          created_at?: string
          daily_graph_index_budget_usd?: number
          daily_ingestion_budget_usd?: number | null
          default_document_visibility?: Database["app"]["Enums"]["document_visibility"]
          graph_bulk_approved_at?: string | null
          graph_bulk_window_ends_at?: string | null
          graph_bulk_window_starts_at?: string | null
          id?: string
          legal_hold_enabled?: boolean
          monthly_graph_maintenance_budget_usd?: number
          monthly_llm_budget_usd?: number | null
          quarantine_byte_cap?: number | null
          quarantine_ttl_hours?: number
          retention_days?: number
          timezone?: string
          updated_at?: string
          upload_quota_bytes?: number | null
          visibility_generation?: number
        }
        Update: {
          authorization_version?: number
          company_name?: string | null
          created_at?: string
          daily_graph_index_budget_usd?: number
          daily_ingestion_budget_usd?: number | null
          default_document_visibility?: Database["app"]["Enums"]["document_visibility"]
          graph_bulk_approved_at?: string | null
          graph_bulk_window_ends_at?: string | null
          graph_bulk_window_starts_at?: string | null
          id?: string
          legal_hold_enabled?: boolean
          monthly_graph_maintenance_budget_usd?: number
          monthly_llm_budget_usd?: number | null
          quarantine_byte_cap?: number | null
          quarantine_ttl_hours?: number
          retention_days?: number
          timezone?: string
          updated_at?: string
          upload_quota_bytes?: number | null
          visibility_generation?: number
        }
        Relationships: []
      }
      conversations: {
        Row: {
          created_at: string
          creator_user_id: string
          deleted_at: string | null
          id: string
          title: string | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          creator_user_id: string
          deleted_at?: string | null
          id?: string
          title?: string | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          creator_user_id?: string
          deleted_at?: string | null
          id?: string
          title?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      crawl_fetch_events: {
        Row: {
          content_type: string | null
          crawl_run_id: string | null
          created_at: string
          decision: string
          decoded_bytes: number
          final_url: string
          id: string
          peer_ip: string | null
          pinned_ips: Json
          policy_version: string
          reason: string
          redirect_hop: number
          requested_url: string
          robots: Json | null
          status_code: number | null
          wire_bytes: number
        }
        Insert: {
          content_type?: string | null
          crawl_run_id?: string | null
          created_at?: string
          decision: string
          decoded_bytes?: number
          final_url: string
          id?: string
          peer_ip?: string | null
          pinned_ips?: Json
          policy_version: string
          reason: string
          redirect_hop?: number
          requested_url: string
          robots?: Json | null
          status_code?: number | null
          wire_bytes?: number
        }
        Update: {
          content_type?: string | null
          crawl_run_id?: string | null
          created_at?: string
          decision?: string
          decoded_bytes?: number
          final_url?: string
          id?: string
          peer_ip?: string | null
          pinned_ips?: Json
          policy_version?: string
          reason?: string
          redirect_hop?: number
          requested_url?: string
          robots?: Json | null
          status_code?: number | null
          wire_bytes?: number
        }
        Relationships: [
          {
            foreignKeyName: "crawl_fetch_events_crawl_run_id_fkey"
            columns: ["crawl_run_id"]
            isOneToOne: false
            referencedRelation: "web_crawl_runs"
            referencedColumns: ["id"]
          },
        ]
      }
      dead_letter_jobs: {
        Row: {
          attempt_count: number
          created_at: string
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          source_job_id: string
          source_table: string
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
        }
        Insert: {
          attempt_count?: number
          created_at?: string
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          heartbeat_at?: string | null
          id?: string
          idempotency_key: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          source_job_id: string
          source_table: string
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
        }
        Update: {
          attempt_count?: number
          created_at?: string
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          heartbeat_at?: string | null
          id?: string
          idempotency_key?: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          source_job_id?: string
          source_table?: string
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
        }
        Relationships: []
      }
      document_acl: {
        Row: {
          created_at: string
          document_id: string
          granted_by: string | null
          grantee_user_id: string
          id: string
          revoked_at: string | null
          updated_at: string
        }
        Insert: {
          created_at?: string
          document_id: string
          granted_by?: string | null
          grantee_user_id: string
          id?: string
          revoked_at?: string | null
          updated_at?: string
        }
        Update: {
          created_at?: string
          document_id?: string
          granted_by?: string | null
          grantee_user_id?: string
          id?: string
          revoked_at?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_acl_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      document_chunks: {
        Row: {
          chunk_index: number
          content_hash: string | null
          contextual_text: string | null
          created_at: string
          deleted_at: string | null
          document_id: string
          duplicate_of_chunk_id: string | null
          embedding: string | null
          id: string
          is_search_representative: boolean
          page_number: number | null
          parent_chunk_id: string | null
          provenance: Json
          raw_text: string
          search_normalized: string | null
          section_path: string[]
          token_count: number | null
          updated_at: string
          version_id: string
        }
        Insert: {
          chunk_index: number
          content_hash?: string | null
          contextual_text?: string | null
          created_at?: string
          deleted_at?: string | null
          document_id: string
          duplicate_of_chunk_id?: string | null
          embedding?: string | null
          id?: string
          is_search_representative?: boolean
          page_number?: number | null
          parent_chunk_id?: string | null
          provenance?: Json
          raw_text: string
          search_normalized?: string | null
          section_path?: string[]
          token_count?: number | null
          updated_at?: string
          version_id: string
        }
        Update: {
          chunk_index?: number
          content_hash?: string | null
          contextual_text?: string | null
          created_at?: string
          deleted_at?: string | null
          document_id?: string
          duplicate_of_chunk_id?: string | null
          embedding?: string | null
          id?: string
          is_search_representative?: boolean
          page_number?: number | null
          parent_chunk_id?: string | null
          provenance?: Json
          raw_text?: string
          search_normalized?: string | null
          section_path?: string[]
          token_count?: number | null
          updated_at?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_chunks_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_chunks_duplicate_of_chunk_id_fkey"
            columns: ["duplicate_of_chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_chunks_parent_chunk_id_fkey"
            columns: ["parent_chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_chunks_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_scan_events: {
        Row: {
          bytes_examined: number | null
          config_version: string | null
          declared_category: string | null
          details: Json
          document_id: string | null
          functionality_level: string | null
          id: string
          network_provenance: Json
          object_hash: string | null
          result: Database["app"]["Enums"]["scan_result"]
          scan_engine_version: string | null
          scanned_at: string
          session_id: string | null
          signature_db_ids: Json
          signature_db_timestamp: string | null
          signature_version: string | null
          uploader_user_id: string | null
          version_id: string | null
        }
        Insert: {
          bytes_examined?: number | null
          config_version?: string | null
          declared_category?: string | null
          details?: Json
          document_id?: string | null
          functionality_level?: string | null
          id?: string
          network_provenance?: Json
          object_hash?: string | null
          result: Database["app"]["Enums"]["scan_result"]
          scan_engine_version?: string | null
          scanned_at?: string
          session_id?: string | null
          signature_db_ids?: Json
          signature_db_timestamp?: string | null
          signature_version?: string | null
          uploader_user_id?: string | null
          version_id?: string | null
        }
        Update: {
          bytes_examined?: number | null
          config_version?: string | null
          declared_category?: string | null
          details?: Json
          document_id?: string | null
          functionality_level?: string | null
          id?: string
          network_provenance?: Json
          object_hash?: string | null
          result?: Database["app"]["Enums"]["scan_result"]
          scan_engine_version?: string | null
          scanned_at?: string
          session_id?: string | null
          signature_db_ids?: Json
          signature_db_timestamp?: string | null
          signature_version?: string | null
          uploader_user_id?: string | null
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "document_scan_events_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_scan_events_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_search_terms: {
        Row: {
          chunk_id: string
          created_at: string
          id: string
          term: string
          term_normalized: string | null
          weight: number
        }
        Insert: {
          chunk_id: string
          created_at?: string
          id?: string
          term: string
          term_normalized?: string | null
          weight?: number
        }
        Update: {
          chunk_id?: string
          created_at?: string
          id?: string
          term?: string
          term_normalized?: string | null
          weight?: number
        }
        Relationships: [
          {
            foreignKeyName: "document_search_terms_chunk_id_fkey"
            columns: ["chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
        ]
      }
      document_sources: {
        Row: {
          approval_required: boolean
          created_at: string
          declared_category: string | null
          document_id: string
          id: string
          source_type: Database["app"]["Enums"]["source_type"]
          source_uri: string | null
          updated_at: string
          version_id: string | null
        }
        Insert: {
          approval_required?: boolean
          created_at?: string
          declared_category?: string | null
          document_id: string
          id?: string
          source_type: Database["app"]["Enums"]["source_type"]
          source_uri?: string | null
          updated_at?: string
          version_id?: string | null
        }
        Update: {
          approval_required?: boolean
          created_at?: string
          declared_category?: string | null
          document_id?: string
          id?: string
          source_type?: Database["app"]["Enums"]["source_type"]
          source_uri?: string | null
          updated_at?: string
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "document_sources_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_sources_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_table_columns: {
        Row: {
          column_name: string
          column_type: string
          created_at: string
          id: string
          ordinal: number
          table_id: string
        }
        Insert: {
          column_name: string
          column_type: string
          created_at?: string
          id?: string
          ordinal: number
          table_id: string
        }
        Update: {
          column_name?: string
          column_type?: string
          created_at?: string
          id?: string
          ordinal?: number
          table_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_table_columns_table_id_fkey"
            columns: ["table_id"]
            isOneToOne: false
            referencedRelation: "document_tables"
            referencedColumns: ["id"]
          },
        ]
      }
      document_tables: {
        Row: {
          column_count: number | null
          created_at: string
          document_id: string
          id: string
          parquet_bucket: string | null
          parquet_path: string | null
          provenance: Json
          row_count: number | null
          sheet_name: string | null
          table_name: string
          updated_at: string
          version_id: string
        }
        Insert: {
          column_count?: number | null
          created_at?: string
          document_id: string
          id?: string
          parquet_bucket?: string | null
          parquet_path?: string | null
          provenance?: Json
          row_count?: number | null
          sheet_name?: string | null
          table_name: string
          updated_at?: string
          version_id: string
        }
        Update: {
          column_count?: number | null
          created_at?: string
          document_id?: string
          id?: string
          parquet_bucket?: string | null
          parquet_path?: string | null
          provenance?: Json
          row_count?: number | null
          sheet_name?: string | null
          table_name?: string
          updated_at?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "document_tables_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "document_tables_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      document_versions: {
        Row: {
          bm25_verified_at: string | null
          byte_size: number | null
          chunk_set_hash: string | null
          content_hash: string | null
          created_at: string
          created_by: string | null
          deleted_at: string | null
          document_id: string
          effective_at: string | null
          embedding_model: string | null
          embedding_policy_hash: string | null
          graph_eligible: boolean
          graph_handoff_at: string | null
          hybrid_verified_at: string | null
          id: string
          is_current: boolean
          language: string | null
          media_type: string | null
          retrieval_eligible: boolean
          status: Database["app"]["Enums"]["document_status"]
          storage_bucket: string | null
          storage_path: string | null
          updated_at: string
          version_number: number
        }
        Insert: {
          bm25_verified_at?: string | null
          byte_size?: number | null
          chunk_set_hash?: string | null
          content_hash?: string | null
          created_at?: string
          created_by?: string | null
          deleted_at?: string | null
          document_id: string
          effective_at?: string | null
          embedding_model?: string | null
          embedding_policy_hash?: string | null
          graph_eligible?: boolean
          graph_handoff_at?: string | null
          hybrid_verified_at?: string | null
          id?: string
          is_current?: boolean
          language?: string | null
          media_type?: string | null
          retrieval_eligible?: boolean
          status?: Database["app"]["Enums"]["document_status"]
          storage_bucket?: string | null
          storage_path?: string | null
          updated_at?: string
          version_number: number
        }
        Update: {
          bm25_verified_at?: string | null
          byte_size?: number | null
          chunk_set_hash?: string | null
          content_hash?: string | null
          created_at?: string
          created_by?: string | null
          deleted_at?: string | null
          document_id?: string
          effective_at?: string | null
          embedding_model?: string | null
          embedding_policy_hash?: string | null
          graph_eligible?: boolean
          graph_handoff_at?: string | null
          hybrid_verified_at?: string | null
          id?: string
          is_current?: boolean
          language?: string | null
          media_type?: string | null
          retrieval_eligible?: boolean
          status?: Database["app"]["Enums"]["document_status"]
          storage_bucket?: string | null
          storage_path?: string | null
          updated_at?: string
          version_number?: number
        }
        Relationships: [
          {
            foreignKeyName: "document_versions_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          created_at: string
          created_by: string | null
          current_version_id: string | null
          deleted_at: string | null
          description: string | null
          graph_eligible: boolean
          id: string
          title: string
          updated_at: string
          visibility: Database["app"]["Enums"]["document_visibility"]
          visibility_generation: number
        }
        Insert: {
          created_at?: string
          created_by?: string | null
          current_version_id?: string | null
          deleted_at?: string | null
          description?: string | null
          graph_eligible?: boolean
          id?: string
          title: string
          updated_at?: string
          visibility?: Database["app"]["Enums"]["document_visibility"]
          visibility_generation?: number
        }
        Update: {
          created_at?: string
          created_by?: string | null
          current_version_id?: string | null
          deleted_at?: string | null
          description?: string | null
          graph_eligible?: boolean
          id?: string
          title?: string
          updated_at?: string
          visibility?: Database["app"]["Enums"]["document_visibility"]
          visibility_generation?: number
        }
        Relationships: [
          {
            foreignKeyName: "documents_current_version_id_fkey"
            columns: ["current_version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      embedding_operation_ledger: {
        Row: {
          actual_usd: number | null
          attempt_count: number
          created_at: string
          dimensions: number
          id: string
          input_count: number
          model: string
          operation_key: string
          policy_hash: string
          provider_request_id: string | null
          reserved_usd: number | null
          result_ref: Json
          status: string
          updated_at: string
          version_id: string
        }
        Insert: {
          actual_usd?: number | null
          attempt_count?: number
          created_at?: string
          dimensions: number
          id?: string
          input_count?: number
          model: string
          operation_key: string
          policy_hash: string
          provider_request_id?: string | null
          reserved_usd?: number | null
          result_ref?: Json
          status?: string
          updated_at?: string
          version_id: string
        }
        Update: {
          actual_usd?: number | null
          attempt_count?: number
          created_at?: string
          dimensions?: number
          id?: string
          input_count?: number
          model?: string
          operation_key?: string
          policy_hash?: string
          provider_request_id?: string | null
          reserved_usd?: number | null
          result_ref?: Json
          status?: string
          updated_at?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "embedding_operation_ledger_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      glossary_aliases: {
        Row: {
          alias: string
          alias_normalized: string | null
          created_at: string
          entry_id: string
          id: string
          language: string
        }
        Insert: {
          alias: string
          alias_normalized?: string | null
          created_at?: string
          entry_id: string
          id?: string
          language: string
        }
        Update: {
          alias?: string
          alias_normalized?: string | null
          created_at?: string
          entry_id?: string
          id?: string
          language?: string
        }
        Relationships: [
          {
            foreignKeyName: "glossary_aliases_entry_id_fkey"
            columns: ["entry_id"]
            isOneToOne: false
            referencedRelation: "glossary_entries"
            referencedColumns: ["id"]
          },
        ]
      }
      glossary_entries: {
        Row: {
          canonical_term: string
          checksum_algorithm: string | null
          created_at: string
          effective_scope: string
          entry_key: string
          entry_type: Database["app"]["Enums"]["glossary_entry_type"]
          id: string
          identifier_pattern: string | null
          import_id: string
          language: string
          term_normalized: string | null
        }
        Insert: {
          canonical_term: string
          checksum_algorithm?: string | null
          created_at?: string
          effective_scope: string
          entry_key: string
          entry_type: Database["app"]["Enums"]["glossary_entry_type"]
          id?: string
          identifier_pattern?: string | null
          import_id: string
          language: string
          term_normalized?: string | null
        }
        Update: {
          canonical_term?: string
          checksum_algorithm?: string | null
          created_at?: string
          effective_scope?: string
          entry_key?: string
          entry_type?: Database["app"]["Enums"]["glossary_entry_type"]
          id?: string
          identifier_pattern?: string | null
          import_id?: string
          language?: string
          term_normalized?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "glossary_entries_import_id_fkey"
            columns: ["import_id"]
            isOneToOne: false
            referencedRelation: "glossary_imports"
            referencedColumns: ["id"]
          },
        ]
      }
      glossary_imports: {
        Row: {
          alias_count: number
          approved_at: string | null
          approved_by: string | null
          created_at: string
          entry_count: number
          id: string
          idempotency_key: string
          imported_by: string
          rolled_back_at: string | null
          rolled_back_by: string | null
          source_name: string
          source_version: string
          status: Database["app"]["Enums"]["glossary_import_status"]
          updated_at: string
        }
        Insert: {
          alias_count?: number
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          entry_count?: number
          id?: string
          idempotency_key: string
          imported_by: string
          rolled_back_at?: string | null
          rolled_back_by?: string | null
          source_name: string
          source_version: string
          status: Database["app"]["Enums"]["glossary_import_status"]
          updated_at?: string
        }
        Update: {
          alias_count?: number
          approved_at?: string | null
          approved_by?: string | null
          created_at?: string
          entry_count?: number
          id?: string
          idempotency_key?: string
          imported_by?: string
          rolled_back_at?: string | null
          rolled_back_by?: string | null
          source_name?: string
          source_version?: string
          status?: Database["app"]["Enums"]["glossary_import_status"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "glossary_imports_approved_by_fkey"
            columns: ["approved_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "glossary_imports_imported_by_fkey"
            columns: ["imported_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "glossary_imports_rolled_back_by_fkey"
            columns: ["rolled_back_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
        ]
      }
      graph_active_workspace_pointer: {
        Row: {
          generation: number
          id: string
          updated_at: string
          workspace_id: string | null
        }
        Insert: {
          generation?: number
          id: string
          updated_at?: string
          workspace_id?: string | null
        }
        Update: {
          generation?: number
          id?: string
          updated_at?: string
          workspace_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "graph_active_workspace_pointer_workspace_id_fkey"
            columns: ["workspace_id"]
            isOneToOne: false
            referencedRelation: "graph_workspaces"
            referencedColumns: ["id"]
          },
        ]
      }
      graph_entity_rules: {
        Row: {
          active: boolean
          alias_scope: string
          aliases: string[]
          approved_at: string | null
          approved_by: string | null
          canonical_name: string | null
          confidence: number | null
          created_at: string
          created_by: string | null
          display_label: string | null
          do_not_merge: string[]
          effective_from: string | null
          effective_until: string | null
          entity_type: string
          id: string
          languages: string[]
          provenance: Json
          reason: string
          relation_label_policy: Database["app"]["Enums"]["graph_relation_label_policy"]
          revoked_at: string | null
          revoked_by: string | null
          row_version: number
          rule: Json
          source: Database["app"]["Enums"]["graph_entity_rule_source"]
          status: Database["app"]["Enums"]["graph_entity_rule_status"]
          updated_at: string
        }
        Insert: {
          active?: boolean
          alias_scope?: string
          aliases?: string[]
          approved_at?: string | null
          approved_by?: string | null
          canonical_name?: string | null
          confidence?: number | null
          created_at?: string
          created_by?: string | null
          display_label?: string | null
          do_not_merge?: string[]
          effective_from?: string | null
          effective_until?: string | null
          entity_type: string
          id?: string
          languages?: string[]
          provenance?: Json
          reason?: string
          relation_label_policy?: Database["app"]["Enums"]["graph_relation_label_policy"]
          revoked_at?: string | null
          revoked_by?: string | null
          row_version?: number
          rule?: Json
          source?: Database["app"]["Enums"]["graph_entity_rule_source"]
          status?: Database["app"]["Enums"]["graph_entity_rule_status"]
          updated_at?: string
        }
        Update: {
          active?: boolean
          alias_scope?: string
          aliases?: string[]
          approved_at?: string | null
          approved_by?: string | null
          canonical_name?: string | null
          confidence?: number | null
          created_at?: string
          created_by?: string | null
          display_label?: string | null
          do_not_merge?: string[]
          effective_from?: string | null
          effective_until?: string | null
          entity_type?: string
          id?: string
          languages?: string[]
          provenance?: Json
          reason?: string
          relation_label_policy?: Database["app"]["Enums"]["graph_relation_label_policy"]
          revoked_at?: string | null
          revoked_by?: string | null
          row_version?: number
          rule?: Json
          source?: Database["app"]["Enums"]["graph_entity_rule_source"]
          status?: Database["app"]["Enums"]["graph_entity_rule_status"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "graph_entity_rules_approved_by_fkey"
            columns: ["approved_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "graph_entity_rules_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
          {
            foreignKeyName: "graph_entity_rules_revoked_by_fkey"
            columns: ["revoked_by"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["user_id"]
          },
        ]
      }
      graph_evidence_map: {
        Row: {
          chunk_id: string
          confidence: number
          config_generation: string | null
          graph_object_id: string
          graph_object_type: string
          id: string
          language: string | null
          mapped_at: string
          method: string | null
          pipeline_version: string | null
          provenance: Json
          score: number | null
          source_hash: string | null
          source_span: Json
          support: number | null
          target_hash: string | null
          target_span: Json
          version_id: string | null
          workspace_key: string | null
        }
        Insert: {
          chunk_id: string
          confidence?: number
          config_generation?: string | null
          graph_object_id: string
          graph_object_type: string
          id?: string
          language?: string | null
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Update: {
          chunk_id?: string
          confidence?: number
          config_generation?: string | null
          graph_object_id?: string
          graph_object_type?: string
          id?: string
          language?: string | null
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "graph_evidence_map_chunk_id_fkey"
            columns: ["chunk_id"]
            isOneToOne: false
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "graph_evidence_map_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      graph_extraction_policy: {
        Row: {
          allowed_entity_types: string[]
          allowed_languages: string[]
          entity_extract_max_gleaning: number
          entity_rules_generation: number
          extraction_policy_hash: string
          id: string
          json_mode: boolean
          relation_label_policy: Database["app"]["Enums"]["graph_relation_label_policy"]
          updated_at: string
        }
        Insert: {
          allowed_entity_types: string[]
          allowed_languages: string[]
          entity_extract_max_gleaning?: number
          entity_rules_generation?: number
          extraction_policy_hash: string
          id: string
          json_mode?: boolean
          relation_label_policy?: Database["app"]["Enums"]["graph_relation_label_policy"]
          updated_at?: string
        }
        Update: {
          allowed_entity_types?: string[]
          allowed_languages?: string[]
          entity_extract_max_gleaning?: number
          entity_rules_generation?: number
          extraction_policy_hash?: string
          id?: string
          json_mode?: boolean
          relation_label_policy?: Database["app"]["Enums"]["graph_relation_label_policy"]
          updated_at?: string
        }
        Relationships: []
      }
      graph_map_repair_jobs: {
        Row: {
          config_generation: string
          created_at: string
          document_id: string | null
          graph_object_id: string
          graph_object_type: string
          id: string
          map_kind: string
          payload_ref: Json
          reason: string
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
          workspace_key: string
        }
        Insert: {
          config_generation: string
          created_at?: string
          document_id?: string | null
          graph_object_id: string
          graph_object_type: string
          id?: string
          map_kind: string
          payload_ref?: Json
          reason: string
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
          workspace_key: string
        }
        Update: {
          config_generation?: string
          created_at?: string
          document_id?: string | null
          graph_object_id?: string
          graph_object_type?: string
          id?: string
          map_kind?: string
          payload_ref?: Json
          reason?: string
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
          workspace_key?: string
        }
        Relationships: [
          {
            foreignKeyName: "graph_map_repair_jobs_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "graph_map_repair_jobs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      graph_mapping_telemetry: {
        Row: {
          config_generation: string
          created_at: string
          denominator: number
          document_id: string | null
          exclusion_count: number
          failure_reason: string | null
          id: string
          language: string | null
          method: string | null
          numerator: number
          object_type: string
          pipeline_version: string
          truncation_count: number
          version_id: string | null
          workspace_key: string
        }
        Insert: {
          config_generation: string
          created_at?: string
          denominator?: number
          document_id?: string | null
          exclusion_count?: number
          failure_reason?: string | null
          id?: string
          language?: string | null
          method?: string | null
          numerator?: number
          object_type: string
          pipeline_version: string
          truncation_count?: number
          version_id?: string | null
          workspace_key: string
        }
        Update: {
          config_generation?: string
          created_at?: string
          denominator?: number
          document_id?: string | null
          exclusion_count?: number
          failure_reason?: string | null
          id?: string
          language?: string | null
          method?: string | null
          numerator?: number
          object_type?: string
          pipeline_version?: string
          truncation_count?: number
          version_id?: string | null
          workspace_key?: string
        }
        Relationships: [
          {
            foreignKeyName: "graph_mapping_telemetry_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "graph_mapping_telemetry_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      graph_survival_samples: {
        Row: {
          id: string
          query_mode: string
          recorded_at: string
          survival_ratio: number
        }
        Insert: {
          id?: string
          query_mode: string
          recorded_at?: string
          survival_ratio: number
        }
        Update: {
          id?: string
          query_mode?: string
          recorded_at?: string
          survival_ratio?: number
        }
        Relationships: []
      }
      graph_workspaces: {
        Row: {
          config_snapshot: Json
          created_at: string
          embedding_dimensions: number
          embedding_model: string
          id: string
          schema_fingerprint: Json
          state: Database["app"]["Enums"]["graph_workspace_state"]
          updated_at: string
          workspace_key: string
        }
        Insert: {
          config_snapshot?: Json
          created_at?: string
          embedding_dimensions?: number
          embedding_model?: string
          id?: string
          schema_fingerprint?: Json
          state: Database["app"]["Enums"]["graph_workspace_state"]
          updated_at?: string
          workspace_key: string
        }
        Update: {
          config_snapshot?: Json
          created_at?: string
          embedding_dimensions?: number
          embedding_model?: string
          id?: string
          schema_fingerprint?: Json
          state?: Database["app"]["Enums"]["graph_workspace_state"]
          updated_at?: string
          workspace_key?: string
        }
        Relationships: []
      }
      graph_writer_lease: {
        Row: {
          expires_at: string | null
          id: string
          owner: string | null
          token: string | null
          updated_at: string
        }
        Insert: {
          expires_at?: string | null
          id: string
          owner?: string | null
          token?: string | null
          updated_at?: string
        }
        Update: {
          expires_at?: string | null
          id?: string
          owner?: string | null
          token?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      ingestion_jobs: {
        Row: {
          attempt_count: number
          created_at: string
          document_id: string | null
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          job_kind: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }
        Insert: {
          attempt_count?: number
          created_at?: string
          document_id?: string | null
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key: string
          job_kind: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Update: {
          attempt_count?: number
          created_at?: string
          document_id?: string | null
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key?: string
          job_kind?: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "ingestion_jobs_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "ingestion_jobs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      job_operation_ledger: {
        Row: {
          created_at: string
          id: string
          job_id: string
          job_table: string
          lease_token: string
          operation_key: string
          result_ref: Json
          status: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          id?: string
          job_id: string
          job_table: string
          lease_token: string
          operation_key: string
          result_ref?: Json
          status: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          id?: string
          job_id?: string
          job_table?: string
          lease_token?: string
          operation_key?: string
          result_ref?: Json
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      lightrag_chunk_map: {
        Row: {
          chunk_id: string
          config_generation: string | null
          language: string | null
          lightrag_chunk_id: string
          lightrag_doc_id: string
          mapped_at: string
          method: string | null
          pipeline_version: string | null
          provenance: Json
          score: number | null
          source_hash: string | null
          source_span: Json
          support: number | null
          target_hash: string | null
          target_span: Json
          version_id: string | null
          workspace_key: string | null
        }
        Insert: {
          chunk_id: string
          config_generation?: string | null
          language?: string | null
          lightrag_chunk_id: string
          lightrag_doc_id: string
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Update: {
          chunk_id?: string
          config_generation?: string | null
          language?: string | null
          lightrag_chunk_id?: string
          lightrag_doc_id?: string
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "lightrag_chunk_map_chunk_id_fkey"
            columns: ["chunk_id"]
            isOneToOne: true
            referencedRelation: "document_chunks"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lightrag_chunk_map_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      lightrag_index_jobs: {
        Row: {
          attempt_count: number
          created_at: string
          document_id: string | null
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          operation: Database["app"]["Enums"]["lightrag_job_operation"]
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }
        Insert: {
          attempt_count?: number
          created_at?: string
          document_id?: string | null
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          operation: Database["app"]["Enums"]["lightrag_job_operation"]
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Update: {
          attempt_count?: number
          created_at?: string
          document_id?: string | null
          error_category?: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes?: number
          heartbeat_at?: string | null
          id?: string
          idempotency_key?: string
          last_error?: string | null
          lease_expires_at?: string | null
          lease_owner?: string | null
          lease_token?: string | null
          max_attempts?: number
          next_attempt_at?: string | null
          operation?: Database["app"]["Enums"]["lightrag_job_operation"]
          payload_ref?: Json
          priority?: Database["app"]["Enums"]["job_priority"]
          status?: Database["app"]["Enums"]["job_status"]
          updated_at?: string
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "lightrag_index_jobs_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lightrag_index_jobs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      lightrag_source_map: {
        Row: {
          config_generation: string | null
          document_id: string
          language: string | null
          lightrag_doc_id: string
          lightrag_workspace: string
          mapped_at: string
          method: string | null
          pipeline_version: string | null
          provenance: Json
          score: number | null
          source_content_hash: string | null
          source_hash: string | null
          source_span: Json
          support: number | null
          target_hash: string | null
          target_span: Json
          version_id: string | null
          workspace_key: string | null
        }
        Insert: {
          config_generation?: string | null
          document_id: string
          language?: string | null
          lightrag_doc_id: string
          lightrag_workspace?: string
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_content_hash?: string | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Update: {
          config_generation?: string | null
          document_id?: string
          language?: string | null
          lightrag_doc_id?: string
          lightrag_workspace?: string
          mapped_at?: string
          method?: string | null
          pipeline_version?: string | null
          provenance?: Json
          score?: number | null
          source_content_hash?: string | null
          source_hash?: string | null
          source_span?: Json
          support?: number | null
          target_hash?: string | null
          target_span?: Json
          version_id?: string | null
          workspace_key?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "lightrag_source_map_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: true
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "lightrag_source_map_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      llm_usage: {
        Row: {
          completion_tokens: number
          cost_usd: number
          id: string
          metadata: Json
          model_id: string
          prompt_tokens: number
          recorded_at: string
          run_id: string | null
          total_tokens: number
          usage_kind: string
          user_id: string | null
        }
        Insert: {
          completion_tokens?: number
          cost_usd?: number
          id?: string
          metadata?: Json
          model_id: string
          prompt_tokens?: number
          recorded_at?: string
          run_id?: string | null
          total_tokens?: number
          usage_kind: string
          user_id?: string | null
        }
        Update: {
          completion_tokens?: number
          cost_usd?: number
          id?: string
          metadata?: Json
          model_id?: string
          prompt_tokens?: number
          recorded_at?: string
          run_id?: string | null
          total_tokens?: number
          usage_kind?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "llm_usage_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      messages: {
        Row: {
          content: string
          conversation_id: string
          created_at: string
          id: string
          role: string
        }
        Insert: {
          content: string
          conversation_id: string
          created_at?: string
          id?: string
          role: string
        }
        Update: {
          content?: string
          conversation_id?: string
          created_at?: string
          id?: string
          role?: string
        }
        Relationships: [
          {
            foreignKeyName: "messages_conversation_id_fkey"
            columns: ["conversation_id"]
            isOneToOne: false
            referencedRelation: "conversations"
            referencedColumns: ["id"]
          },
        ]
      }
      mfa_recovery_requests: {
        Row: {
          completed_at: string | null
          created_at: string
          id: string
          initiated_by: string | null
          status: string
          subject_user_id: string
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          id?: string
          initiated_by?: string | null
          status?: string
          subject_user_id: string
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          id?: string
          initiated_by?: string | null
          status?: string
          subject_user_id?: string
        }
        Relationships: []
      }
      mfa_recovery_verifications: {
        Row: {
          expires_at: string
          recovery_request_id: string
          subject_user_id: string
          verification_method: string
          verification_reference: string
          verified_at: string
          verified_by: string
        }
        Insert: {
          expires_at?: string
          recovery_request_id: string
          subject_user_id: string
          verification_method: string
          verification_reference: string
          verified_at?: string
          verified_by: string
        }
        Update: {
          expires_at?: string
          recovery_request_id?: string
          subject_user_id?: string
          verification_method?: string
          verification_reference?: string
          verified_at?: string
          verified_by?: string
        }
        Relationships: []
      }
      offboarding_requests: {
        Row: {
          completed_at: string | null
          created_at: string
          id: string
          requested_by: string | null
          status: string
          subject_user_id: string
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          id?: string
          requested_by?: string | null
          status?: string
          subject_user_id: string
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          id?: string
          requested_by?: string | null
          status?: string
          subject_user_id?: string
        }
        Relationships: []
      }
      profiles: {
        Row: {
          created_at: string
          daily_ingestion_budget_usd: number | null
          disabled_at: string | null
          display_name: string | null
          mfa_enrolled: boolean
          monthly_llm_budget_usd: number | null
          role: Database["app"]["Enums"]["user_role"]
          session_revoked_at: string | null
          updated_at: string
          upload_enabled: boolean
          upload_quota_bytes: number | null
          user_id: string
        }
        Insert: {
          created_at?: string
          daily_ingestion_budget_usd?: number | null
          disabled_at?: string | null
          display_name?: string | null
          mfa_enrolled?: boolean
          monthly_llm_budget_usd?: number | null
          role?: Database["app"]["Enums"]["user_role"]
          session_revoked_at?: string | null
          updated_at?: string
          upload_enabled?: boolean
          upload_quota_bytes?: number | null
          user_id: string
        }
        Update: {
          created_at?: string
          daily_ingestion_budget_usd?: number | null
          disabled_at?: string | null
          display_name?: string | null
          mfa_enrolled?: boolean
          monthly_llm_budget_usd?: number | null
          role?: Database["app"]["Enums"]["user_role"]
          session_revoked_at?: string | null
          updated_at?: string
          upload_enabled?: boolean
          upload_quota_bytes?: number | null
          user_id?: string
        }
        Relationships: []
      }
      restricted_read_events: {
        Row: {
          actor_user_id: string | null
          audit_event_id: string | null
          created_at: string
          document_id: string | null
          id: string
          purpose: string
          run_id: string | null
          signed_url_expires_at: string | null
          version_id: string | null
        }
        Insert: {
          actor_user_id?: string | null
          audit_event_id?: string | null
          created_at?: string
          document_id?: string | null
          id?: string
          purpose: string
          run_id?: string | null
          signed_url_expires_at?: string | null
          version_id?: string | null
        }
        Update: {
          actor_user_id?: string | null
          audit_event_id?: string | null
          created_at?: string
          document_id?: string | null
          id?: string
          purpose?: string
          run_id?: string | null
          signed_url_expires_at?: string | null
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "restricted_read_events_audit_event_id_fkey"
            columns: ["audit_event_id"]
            isOneToOne: false
            referencedRelation: "audit_events"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "restricted_read_events_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "restricted_read_events_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "restricted_read_events_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      retention_holds: {
        Row: {
          created_at: string
          held_by: string | null
          id: string
          reason: string
          released_at: string | null
          resource_id: string
          resource_type: string
        }
        Insert: {
          created_at?: string
          held_by?: string | null
          id?: string
          reason: string
          released_at?: string | null
          resource_id: string
          resource_type: string
        }
        Update: {
          created_at?: string
          held_by?: string | null
          id?: string
          reason?: string
          released_at?: string | null
          resource_id?: string
          resource_type?: string
        }
        Relationships: []
      }
      revoked_sessions: {
        Row: {
          revoked_at: string
          session_id: string
          user_id: string
        }
        Insert: {
          revoked_at?: string
          session_id: string
          user_id: string
        }
        Update: {
          revoked_at?: string
          session_id?: string
          user_id?: string
        }
        Relationships: []
      }
      runs: {
        Row: {
          completed_at: string | null
          conversation_id: string
          created_at: string
          creator_user_id: string
          graph_name: string | null
          id: string
          idempotency_key: string | null
          started_at: string | null
          status: Database["app"]["Enums"]["run_status"]
          updated_at: string
        }
        Insert: {
          completed_at?: string | null
          conversation_id: string
          created_at?: string
          creator_user_id: string
          graph_name?: string | null
          id?: string
          idempotency_key?: string | null
          started_at?: string | null
          status?: Database["app"]["Enums"]["run_status"]
          updated_at?: string
        }
        Update: {
          completed_at?: string | null
          conversation_id?: string
          created_at?: string
          creator_user_id?: string
          graph_name?: string | null
          id?: string
          idempotency_key?: string | null
          started_at?: string | null
          status?: Database["app"]["Enums"]["run_status"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "runs_conversation_id_fkey"
            columns: ["conversation_id"]
            isOneToOne: false
            referencedRelation: "conversations"
            referencedColumns: ["id"]
          },
        ]
      }
      search_aliases: {
        Row: {
          alias: string
          alias_normalized: string | null
          canonical_term: string
          created_at: string
          effective_scope: string | null
          glossary_entry_id: string | null
          id: string
          import_id: string | null
          language: string | null
          updated_at: string
        }
        Insert: {
          alias: string
          alias_normalized?: string | null
          canonical_term: string
          created_at?: string
          effective_scope?: string | null
          glossary_entry_id?: string | null
          id?: string
          import_id?: string | null
          language?: string | null
          updated_at?: string
        }
        Update: {
          alias?: string
          alias_normalized?: string | null
          canonical_term?: string
          created_at?: string
          effective_scope?: string | null
          glossary_entry_id?: string | null
          id?: string
          import_id?: string | null
          language?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "search_aliases_glossary_entry_id_fkey"
            columns: ["glossary_entry_id"]
            isOneToOne: false
            referencedRelation: "glossary_entries"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "search_aliases_import_id_fkey"
            columns: ["import_id"]
            isOneToOne: false
            referencedRelation: "glossary_imports"
            referencedColumns: ["id"]
          },
        ]
      }
      source_approval_requests: {
        Row: {
          created_at: string
          domain: string | null
          expires_at: string | null
          id: string
          max_depth: number
          max_pages: number
          policy_version: string | null
          requested_by: string | null
          review_notes: string | null
          reviewed_by: string | null
          source_id: string | null
          start_url: string | null
          status: Database["app"]["Enums"]["approval_status"]
          updated_at: string
        }
        Insert: {
          created_at?: string
          domain?: string | null
          expires_at?: string | null
          id?: string
          max_depth?: number
          max_pages?: number
          policy_version?: string | null
          requested_by?: string | null
          review_notes?: string | null
          reviewed_by?: string | null
          source_id?: string | null
          start_url?: string | null
          status?: Database["app"]["Enums"]["approval_status"]
          updated_at?: string
        }
        Update: {
          created_at?: string
          domain?: string | null
          expires_at?: string | null
          id?: string
          max_depth?: number
          max_pages?: number
          policy_version?: string | null
          requested_by?: string | null
          review_notes?: string | null
          reviewed_by?: string | null
          source_id?: string | null
          start_url?: string | null
          status?: Database["app"]["Enums"]["approval_status"]
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "source_approval_requests_source_id_fkey"
            columns: ["source_id"]
            isOneToOne: false
            referencedRelation: "document_sources"
            referencedColumns: ["id"]
          },
        ]
      }
      storage_promotion_sagas: {
        Row: {
          completed_at: string | null
          created_at: string
          current_step: string
          destination_bucket: string
          destination_path: string
          expected_bytes: number
          expected_hash: string
          id: string
          idempotency_key: string
          quarantine_bucket: string
          quarantine_path: string
          reservation_id: string | null
          updated_at: string
          version_id: string
        }
        Insert: {
          completed_at?: string | null
          created_at?: string
          current_step?: string
          destination_bucket: string
          destination_path: string
          expected_bytes: number
          expected_hash: string
          id?: string
          idempotency_key: string
          quarantine_bucket: string
          quarantine_path: string
          reservation_id?: string | null
          updated_at?: string
          version_id: string
        }
        Update: {
          completed_at?: string | null
          created_at?: string
          current_step?: string
          destination_bucket?: string
          destination_path?: string
          expected_bytes?: number
          expected_hash?: string
          id?: string
          idempotency_key?: string
          quarantine_bucket?: string
          quarantine_path?: string
          reservation_id?: string | null
          updated_at?: string
          version_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "storage_promotion_sagas_reservation_id_fkey"
            columns: ["reservation_id"]
            isOneToOne: false
            referencedRelation: "upload_quota_reservations"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "storage_promotion_sagas_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      team_invitations: {
        Row: {
          accepted_at: string | null
          accepted_by: string | null
          created_at: string
          email: string
          expires_at: string
          id: string
          invited_by: string | null
          revoked_at: string | null
          role: Database["app"]["Enums"]["user_role"]
          token_hash: string
          updated_at: string
          upload_enabled: boolean
        }
        Insert: {
          accepted_at?: string | null
          accepted_by?: string | null
          created_at?: string
          email: string
          expires_at: string
          id?: string
          invited_by?: string | null
          revoked_at?: string | null
          role?: Database["app"]["Enums"]["user_role"]
          token_hash: string
          updated_at?: string
          upload_enabled?: boolean
        }
        Update: {
          accepted_at?: string | null
          accepted_by?: string | null
          created_at?: string
          email?: string
          expires_at?: string
          id?: string
          invited_by?: string | null
          revoked_at?: string | null
          role?: Database["app"]["Enums"]["user_role"]
          token_hash?: string
          updated_at?: string
          upload_enabled?: boolean
        }
        Relationships: []
      }
      tool_catalog: {
        Row: {
          active: boolean
          created_at: string
          description: string | null
          display_name: string
          id: string
          tool_key: string
          updated_at: string
        }
        Insert: {
          active?: boolean
          created_at?: string
          description?: string | null
          display_name: string
          id?: string
          tool_key: string
          updated_at?: string
        }
        Update: {
          active?: boolean
          created_at?: string
          description?: string | null
          display_name?: string
          id?: string
          tool_key?: string
          updated_at?: string
        }
        Relationships: []
      }
      tool_permissions: {
        Row: {
          created_at: string
          id: string
          permission: Database["app"]["Enums"]["tool_permission_level"]
          role: Database["app"]["Enums"]["user_role"] | null
          tool_id: string
          updated_at: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          id?: string
          permission?: Database["app"]["Enums"]["tool_permission_level"]
          role?: Database["app"]["Enums"]["user_role"] | null
          tool_id: string
          updated_at?: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          id?: string
          permission?: Database["app"]["Enums"]["tool_permission_level"]
          role?: Database["app"]["Enums"]["user_role"] | null
          tool_id?: string
          updated_at?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "tool_permissions_tool_id_fkey"
            columns: ["tool_id"]
            isOneToOne: false
            referencedRelation: "tool_catalog"
            referencedColumns: ["id"]
          },
        ]
      }
      tool_usage_events: {
        Row: {
          created_at: string
          event_kind: string
          id: string
          metadata: Json
          run_id: string | null
          tool_id: string
          user_id: string | null
        }
        Insert: {
          created_at?: string
          event_kind: string
          id?: string
          metadata?: Json
          run_id?: string | null
          tool_id: string
          user_id?: string | null
        }
        Update: {
          created_at?: string
          event_kind?: string
          id?: string
          metadata?: Json
          run_id?: string | null
          tool_id?: string
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "tool_usage_events_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "tool_usage_events_tool_id_fkey"
            columns: ["tool_id"]
            isOneToOne: false
            referencedRelation: "tool_catalog"
            referencedColumns: ["id"]
          },
        ]
      }
      tool_versions: {
        Row: {
          active: boolean
          created_at: string
          id: string
          schema: Json
          tool_id: string
          version_label: string
        }
        Insert: {
          active?: boolean
          created_at?: string
          id?: string
          schema?: Json
          tool_id: string
          version_label: string
        }
        Update: {
          active?: boolean
          created_at?: string
          id?: string
          schema?: Json
          tool_id?: string
          version_label?: string
        }
        Relationships: [
          {
            foreignKeyName: "tool_versions_tool_id_fkey"
            columns: ["tool_id"]
            isOneToOne: false
            referencedRelation: "tool_catalog"
            referencedColumns: ["id"]
          },
        ]
      }
      upload_quota_reservations: {
        Row: {
          actual_bytes: number | null
          cleanup_status: string | null
          committed_at: string | null
          created_at: string
          document_id: string | null
          expires_at: string
          finalized_at: string | null
          id: string
          idempotency_key: string | null
          released_at: string | null
          reserved_bytes: number
          session_id: string | null
          status: Database["app"]["Enums"]["budget_reservation_status"]
          storage_bucket: string | null
          storage_path: string | null
          updated_at: string
          user_id: string
          version_id: string | null
        }
        Insert: {
          actual_bytes?: number | null
          cleanup_status?: string | null
          committed_at?: string | null
          created_at?: string
          document_id?: string | null
          expires_at: string
          finalized_at?: string | null
          id?: string
          idempotency_key?: string | null
          released_at?: string | null
          reserved_bytes: number
          session_id?: string | null
          status?: Database["app"]["Enums"]["budget_reservation_status"]
          storage_bucket?: string | null
          storage_path?: string | null
          updated_at?: string
          user_id: string
          version_id?: string | null
        }
        Update: {
          actual_bytes?: number | null
          cleanup_status?: string | null
          committed_at?: string | null
          created_at?: string
          document_id?: string | null
          expires_at?: string
          finalized_at?: string | null
          id?: string
          idempotency_key?: string | null
          released_at?: string | null
          reserved_bytes?: number
          session_id?: string | null
          status?: Database["app"]["Enums"]["budget_reservation_status"]
          storage_bucket?: string | null
          storage_path?: string | null
          updated_at?: string
          user_id?: string
          version_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "upload_quota_reservations_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "upload_quota_reservations_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      user_feedback: {
        Row: {
          comment: string | null
          created_at: string
          id: string
          rating: number | null
          run_id: string
          user_id: string
        }
        Insert: {
          comment?: string | null
          created_at?: string
          id?: string
          rating?: number | null
          run_id: string
          user_id: string
        }
        Update: {
          comment?: string | null
          created_at?: string
          id?: string
          rating?: number | null
          run_id?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_feedback_run_id_fkey"
            columns: ["run_id"]
            isOneToOne: false
            referencedRelation: "runs"
            referencedColumns: ["id"]
          },
        ]
      }
      web_crawl_runs: {
        Row: {
          completed_at: string | null
          crawl_version: number
          created_at: string
          decoded_bytes_total: number
          failure_reason: string | null
          id: string
          pages_fetched: number
          policy_version: string
          source_id: string
          start_url: string
          started_at: string
          status: string
          updated_at: string
          version_id: string | null
          wire_bytes_total: number
        }
        Insert: {
          completed_at?: string | null
          crawl_version: number
          created_at?: string
          decoded_bytes_total?: number
          failure_reason?: string | null
          id?: string
          pages_fetched?: number
          policy_version: string
          source_id: string
          start_url: string
          started_at?: string
          status?: string
          updated_at?: string
          version_id?: string | null
          wire_bytes_total?: number
        }
        Update: {
          completed_at?: string | null
          crawl_version?: number
          created_at?: string
          decoded_bytes_total?: number
          failure_reason?: string | null
          id?: string
          pages_fetched?: number
          policy_version?: string
          source_id?: string
          start_url?: string
          started_at?: string
          status?: string
          updated_at?: string
          version_id?: string | null
          wire_bytes_total?: number
        }
        Relationships: [
          {
            foreignKeyName: "web_crawl_runs_source_id_fkey"
            columns: ["source_id"]
            isOneToOne: false
            referencedRelation: "document_sources"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "web_crawl_runs_version_id_fkey"
            columns: ["version_id"]
            isOneToOne: false
            referencedRelation: "document_versions"
            referencedColumns: ["id"]
          },
        ]
      }
      web_snapshots: {
        Row: {
          canonical_url: string
          content_hash: string
          content_type: string | null
          crawl_run_id: string
          created_at: string
          decoded_bytes: number
          fetched_at: string
          id: string
          peer_ip: string | null
          pinned_ips: Json
          redirect_chain: Json
          source_id: string
          storage_bucket: string
          storage_path: string
          title: string | null
          wire_bytes: number
        }
        Insert: {
          canonical_url: string
          content_hash: string
          content_type?: string | null
          crawl_run_id: string
          created_at?: string
          decoded_bytes?: number
          fetched_at?: string
          id?: string
          peer_ip?: string | null
          pinned_ips?: Json
          redirect_chain?: Json
          source_id: string
          storage_bucket: string
          storage_path: string
          title?: string | null
          wire_bytes?: number
        }
        Update: {
          canonical_url?: string
          content_hash?: string
          content_type?: string | null
          crawl_run_id?: string
          created_at?: string
          decoded_bytes?: number
          fetched_at?: string
          id?: string
          peer_ip?: string | null
          pinned_ips?: Json
          redirect_chain?: Json
          source_id?: string
          storage_bucket?: string
          storage_path?: string
          title?: string | null
          wire_bytes?: number
        }
        Relationships: [
          {
            foreignKeyName: "web_snapshots_crawl_run_id_fkey"
            columns: ["crawl_run_id"]
            isOneToOne: false
            referencedRelation: "web_crawl_runs"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "web_snapshots_source_id_fkey"
            columns: ["source_id"]
            isOneToOne: false
            referencedRelation: "document_sources"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      company_health: {
        Row: {
          authorization_version: number | null
          default_document_visibility:
            | Database["app"]["Enums"]["document_visibility"]
            | null
          updated_at: string | null
          visibility_generation: number | null
        }
        Insert: {
          authorization_version?: number | null
          default_document_visibility?:
            | Database["app"]["Enums"]["document_visibility"]
            | null
          updated_at?: string | null
          visibility_generation?: number | null
        }
        Update: {
          authorization_version?: number | null
          default_document_visibility?:
            | Database["app"]["Enums"]["document_visibility"]
            | null
          updated_at?: string | null
          visibility_generation?: number | null
        }
        Relationships: []
      }
    }
    Functions: {
      _graph_entity_rule_require_admin: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
        }
        Returns: {
          created_at: string
          daily_ingestion_budget_usd: number | null
          disabled_at: string | null
          display_name: string | null
          mfa_enrolled: boolean
          monthly_llm_budget_usd: number | null
          role: Database["app"]["Enums"]["user_role"]
          session_revoked_at: string | null
          updated_at: string
          upload_enabled: boolean
          upload_quota_bytes: number | null
          user_id: string
        }
        SetofOptions: {
          from: "*"
          to: "profiles"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      _validate_job_lease_seconds: {
        Args: { p_lease_seconds: number }
        Returns: undefined
      }
      _validate_job_owner: { Args: { p_owner: string }; Returns: undefined }
      accept_invitation: {
        Args: { p_token_hash: string; p_user_email: string; p_user_id: string }
        Returns: string
      }
      activate_graph_ineligible_version: {
        Args: { p_version_id: string }
        Returns: {
          created_at: string
          created_by: string | null
          current_version_id: string | null
          deleted_at: string | null
          description: string | null
          graph_eligible: boolean
          id: string
          title: string
          updated_at: string
          visibility: Database["app"]["Enums"]["document_visibility"]
          visibility_generation: number
        }
        SetofOptions: {
          from: "*"
          to: "documents"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      advance_promotion_saga_step: {
        Args: { p_expected_step: string; p_new_step: string; p_saga_id: string }
        Returns: boolean
      }
      append_audit_event: {
        Args: {
          p_actor_role: Database["app"]["Enums"]["user_role"]
          p_actor_user_id: string
          p_authorization_version: number
          p_event_type: string
          p_payload?: Json
          p_purpose?: string
          p_resource_id?: string
          p_resource_type?: string
          p_session_id?: string
          p_target_id: string
          p_target_type: string
        }
        Returns: string
      }
      apply_entity_rule_graph_invalidation: {
        Args: { p_reason: string }
        Returns: {
          entity_rules_generation: number
          rebuild_job_id: string
          repair_job_id: string
        }[]
      }
      approve_glossary_import: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          target_import_id: string
        }
        Returns: {
          alias_count: number
          entry_count: number
          import_id: string
          status: Database["app"]["Enums"]["glossary_import_status"]
        }[]
      }
      approve_graph_entity_rule: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_payload: Json
          p_row_version: number
          p_rule_id: string
        }
        Returns: {
          entity_rules_generation: number
          invalidated: boolean
          rebuild_job_id: string
          repair_job_id: string
          row_version: number
          rule_id: string
          status: Database["app"]["Enums"]["graph_entity_rule_status"]
        }[]
      }
      assert_graph_index_allowed: {
        Args: { p_document_id: string; p_version_id?: string }
        Returns: boolean
      }
      audit_event_canonical_material: {
        Args: {
          p_actor_role: Database["app"]["Enums"]["user_role"]
          p_actor_user_id: string
          p_authorization_version: number
          p_created_at: string
          p_event_type: string
          p_payload: Json
          p_previous_hash: string
          p_purpose: string
          p_resource_id: string
          p_resource_type: string
          p_session_id: string
          p_target_id: string
          p_target_type: string
          p_visibility_generation: number
        }
        Returns: string
      }
      authorize_restricted_read: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_document_id: string
          p_purpose: string
          p_session_id: string
          p_signed_url_expires_at?: string
          p_version_id: string
        }
        Returns: string
      }
      bootstrap_owner: { Args: { p_user_id: string }; Returns: boolean }
      caller_can_read_document: {
        Args: {
          caller_role: string
          caller_user_id: string
          p_document_id: string
        }
        Returns: boolean
      }
      cancel_ingestion_job: {
        Args: { p_job_id: string; p_lease_token: string; p_owner: string }
        Returns: boolean
      }
      claim_bm25_index_job: {
        Args: { p_lease_seconds: number; p_owner: string }
        Returns: {
          attempt_count: number
          chunk_id: string | null
          created_at: string
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          operation: Database["app"]["Enums"]["bm25_job_operation"]
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }[]
        SetofOptions: {
          from: "*"
          to: "bm25_index_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      claim_ingestion_job: {
        Args: { p_lease_seconds: number; p_owner: string }
        Returns: {
          attempt_count: number
          created_at: string
          document_id: string | null
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          job_kind: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }[]
        SetofOptions: {
          from: "*"
          to: "ingestion_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      claim_lightrag_index_job: {
        Args: { p_lease_seconds: number; p_owner: string }
        Returns: {
          attempt_count: number
          created_at: string
          document_id: string | null
          error_category: Database["app"]["Enums"]["job_error_category"] | null
          estimated_size_bytes: number
          heartbeat_at: string | null
          id: string
          idempotency_key: string
          last_error: string | null
          lease_expires_at: string | null
          lease_owner: string | null
          lease_token: string | null
          max_attempts: number
          next_attempt_at: string | null
          operation: Database["app"]["Enums"]["lightrag_job_operation"]
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string | null
        }[]
        SetofOptions: {
          from: "*"
          to: "lightrag_index_jobs"
          isOneToOne: false
          isSetofReturn: true
        }
      }
      complete_ingestion_job: {
        Args: { p_job_id: string; p_lease_token: string; p_owner: string }
        Returns: boolean
      }
      complete_lightrag_index_job: {
        Args: {
          p_job_id: string
          p_lease_token: string
          p_owner: string
          p_result?: Json
        }
        Returns: boolean
      }
      complete_promotion_db_switch: {
        Args: {
          p_byte_size: number
          p_content_hash: string
          p_destination_bucket: string
          p_destination_path: string
          p_media_type: string
          p_saga_id: string
          p_version_id: string
        }
        Returns: boolean
      }
      count_authorized_retrievable_chunks: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_language?: string
        }
        Returns: number
      }
      current_authorization_version: { Args: never; Returns: number }
      emit_admin_notification: {
        Args: {
          body: string
          kind: string
          metadata?: Json
          severity: string
          title: string
        }
        Returns: string
      }
      emit_graph_acl_remove_for_document: {
        Args: { p_document_id: string }
        Returns: undefined
      }
      enqueue_approved_website_crawl: {
        Args: {
          approved_domain: string
          attestation_policy_version?: string
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          content_class?: string
          document_title: string
          graph_eligible?: boolean
          idempotency_key: string
          max_depth?: number
          max_pages?: number
          start_url: string
        }
        Returns: {
          approval_id: string
          document_id: string
          job_id: string
          source_id: string
          version_id: string
        }[]
      }
      enqueue_bm25_projection_for_version: {
        Args: {
          p_chunk_set_hash: string
          p_operation_key?: string
          p_version_id: string
        }
        Returns: string
      }
      enqueue_graph_map_repair: {
        Args: {
          p_config_generation: string
          p_document_id: string
          p_map_kind: string
          p_object_id: string
          p_object_type: string
          p_reason: string
          p_version_id: string
          p_workspace_key: string
        }
        Returns: string
      }
      enqueue_graph_pending_handoff: {
        Args: {
          p_content_hash?: string
          p_lightrag_version?: string
          p_pipeline_version?: string
          p_version_id: string
        }
        Returns: string
      }
      enqueue_graph_reconciliation_job: {
        Args: {
          p_reason: string
          p_source_job_id: string
          p_workspace_key: string
        }
        Returns: string
      }
      exclude_version_from_retrieval: {
        Args: { p_reason?: string; p_version_id: string }
        Returns: {
          bm25_verified_at: string | null
          byte_size: number | null
          chunk_set_hash: string | null
          content_hash: string | null
          created_at: string
          created_by: string | null
          deleted_at: string | null
          document_id: string
          effective_at: string | null
          embedding_model: string | null
          embedding_policy_hash: string | null
          graph_eligible: boolean
          graph_handoff_at: string | null
          hybrid_verified_at: string | null
          id: string
          is_current: boolean
          language: string | null
          media_type: string | null
          retrieval_eligible: boolean
          status: Database["app"]["Enums"]["document_status"]
          storage_bucket: string | null
          storage_path: string | null
          updated_at: string
          version_number: number
        }
        SetofOptions: {
          from: "*"
          to: "document_versions"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      fail_lightrag_index_job: {
        Args: {
          p_error_category: Database["app"]["Enums"]["job_error_category"]
          p_job_id: string
          p_last_error: string
          p_lease_token: string
          p_next_attempt_at: string
          p_owner: string
          p_status: Database["app"]["Enums"]["job_status"]
        }
        Returns: boolean
      }
      fetch_authorized_chunk_context: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_chunk_ids: string[]
        }
        Returns: {
          chunk_id: string
          chunk_index: number
          document_id: string
          is_search_representative: boolean
          page_number: number
          parent_chunk_id: string
          provenance: Json
          raw_text: string
          section_path: string[]
          token_count: number
          version_id: string
        }[]
      }
      finalize_hybrid_ready: {
        Args: {
          p_bm25_job_id?: string
          p_chunk_set_hash: string
          p_version_id: string
        }
        Returns: {
          bm25_verified_at: string | null
          byte_size: number | null
          chunk_set_hash: string | null
          content_hash: string | null
          created_at: string
          created_by: string | null
          deleted_at: string | null
          document_id: string
          effective_at: string | null
          embedding_model: string | null
          embedding_policy_hash: string | null
          graph_eligible: boolean
          graph_handoff_at: string | null
          hybrid_verified_at: string | null
          id: string
          is_current: boolean
          language: string | null
          media_type: string | null
          retrieval_eligible: boolean
          status: Database["app"]["Enums"]["document_status"]
          storage_bucket: string | null
          storage_path: string | null
          updated_at: string
          version_number: number
        }
        SetofOptions: {
          from: "*"
          to: "document_versions"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      finalize_quarantine_upload: {
        Args: {
          actual_bytes: number
          attestation_policy_version: string
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          content_hash: string
          declared_category: string
          document_title?: string
          idempotency_key: string
          media_type: string
          object_name: string
          reservation_id: string
        }
        Returns: {
          document_id: string
          job_id: string
          version_id: string
        }[]
      }
      finalize_upload_quota: {
        Args: {
          actual_bytes: number
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_reservation_id: string
        }
        Returns: {
          cleanup_status: string
          over_limit: boolean
          recorded_actual_bytes: number
          reservation_id: string
          reserved_bytes: number
          status: Database["app"]["Enums"]["budget_reservation_status"]
        }[]
      }
      glossary_identifier_rule_rejected: {
        Args: { pattern: string }
        Returns: boolean
      }
      glossary_payload_has_cycle: { Args: { payload: Json }; Returns: boolean }
      graph_entity_rule_has_conflict: {
        Args: {
          p_aliases: string[]
          p_canonical: string
          p_do_not_merge: string[]
          p_entity_type: string
          p_rule_id: string
        }
        Returns: string
      }
      graph_visibility_counts: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_relevant_version_ids?: string[]
        }
        Returns: {
          acl_blindness_count: number
          partial_readiness_count: number
        }[]
      }
      heartbeat_graph_writer_lease: {
        Args: { p_lease_seconds: number; p_owner: string; p_token: string }
        Returns: boolean
      }
      heartbeat_ingestion_job: {
        Args: {
          p_job_id: string
          p_lease_seconds: number
          p_lease_token: string
          p_owner: string
        }
        Returns: boolean
      }
      heartbeat_lightrag_index_job: {
        Args: {
          p_job_id: string
          p_lease_seconds: number
          p_lease_token: string
          p_owner: string
        }
        Returns: boolean
      }
      import_glossary_batch: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          idempotency_key: string
          payload: Json
          source_name: string
          source_version: string
        }
        Returns: {
          alias_count: number
          entry_count: number
          import_id: string
          status: Database["app"]["Enums"]["glossary_import_status"]
        }[]
      }
      inspect_graph_neighborhood: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_config_generation: string
          p_depth: number
          p_document_id: string
          p_entity_keys: string[]
          p_row_limit: number
          p_workspace_key: string
        }
        Returns: {
          chunk_id: string
          document_id: string
          hop: number
          object_id: string
          object_type: string
          support: number
          version_id: string
        }[]
      }
      list_graph_entity_rules: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
        }
        Returns: {
          active: boolean
          alias_scope: string
          aliases: string[]
          canonical_name: string
          confidence: number
          created_at: string
          display_label: string
          do_not_merge: string[]
          entity_type: string
          id: string
          languages: string[]
          reason: string
          relation_label_policy: Database["app"]["Enums"]["graph_relation_label_policy"]
          row_version: number
          source: Database["app"]["Enums"]["graph_entity_rule_source"]
          status: Database["app"]["Enums"]["graph_entity_rule_status"]
          updated_at: string
        }[]
      }
      list_quarantine_cleanup_candidates: {
        Args: { as_of?: string; result_limit?: number }
        Returns: {
          actual_bytes: number
          cleanup_status: string
          reason: string
          reservation_id: string
          reserved_bytes: number
          storage_bucket: string
          storage_path: string
          user_id: string
        }[]
      }
      list_user_conversations: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
        }
        Returns: {
          creator_user_id: string
          id: string
          title: string
        }[]
      }
      list_visible_documents: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
        }
        Returns: {
          current_version_id: string
          id: string
          title: string
          visibility: Database["app"]["Enums"]["document_visibility"]
          visibility_generation: number
        }[]
      }
      load_active_crawl_approval: {
        Args: { p_source_id: string }
        Returns: {
          approval_id: string
          approved_domain: string
          max_depth: number
          max_pages: number
          policy_version: string
          requester_user_id: string
          reviewer_user_id: string
          source_id: string
          start_url: string
        }[]
      }
      mark_quarantine_cleanup_done: {
        Args: { p_reservation_id: string }
        Returns: undefined
      }
      occupy_graph_writer_lease: {
        Args: { p_lease_seconds: number; p_owner: string; p_token: string }
        Returns: boolean
      }
      quarantine_graph_workspace: {
        Args: { p_reason: string; p_workspace_key: string }
        Returns: string
      }
      quarantine_upload_path_allowed: {
        Args: { object_name: string }
        Returns: boolean
      }
      recheck_retrieval_candidates: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_chunk_ids: string[]
        }
        Returns: {
          chunk_id: string
          document_id: string
          version_id: string
        }[]
      }
      record_embedding_ledger: {
        Args: {
          p_actual_usd?: number
          p_dimensions: number
          p_input_count: number
          p_model: string
          p_operation_key: string
          p_policy_hash: string
          p_provider_request_id?: string
          p_reserved_usd?: number
          p_result_ref?: Json
          p_status: string
          p_version_id: string
        }
        Returns: string
      }
      record_job_operation_ledger: {
        Args: {
          p_job_id: string
          p_job_table: string
          p_lease_token: string
          p_operation_key: string
          p_result_ref?: Json
          p_status: string
        }
        Returns: string
      }
      redact_audit_payload: { Args: { payload: Json }; Returns: Json }
      release_expired_upload_reservations: {
        Args: { as_of?: string }
        Returns: number
      }
      release_graph_writer_lease: {
        Args: { p_owner: string; p_token: string }
        Returns: boolean
      }
      reserve_upload_quota: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          declared_bytes: number
          idempotency_key: string
          session_id: string
          storage_path?: string
        }
        Returns: {
          document_id: string
          expires_at: string
          reservation_id: string
          reserved_bytes: number
          reserved_storage_path: string
          storage_bucket: string
          version_id: string
        }[]
      }
      resolve_structured_table: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_table_id: string
          p_version_id: string
        }
        Returns: {
          column_count: number
          document_id: string
          parquet_bucket: string
          parquet_path: string
          provenance: Json
          row_count: number
          sheet_name: string
          table_id: string
          table_name: string
          version_id: string
        }[]
      }
      retrieval_exact_row_cap: { Args: never; Returns: number }
      retrieve_dense_candidates: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_candidate_limit: number
          p_language?: string
          p_mode: string
          p_profile: string
          p_query_embedding: string
        }
        Returns: {
          chunk_id: string
          distance: number
          document_id: string
          retrieval_mode: string
          version_id: string
        }[]
      }
      retrieve_term_candidates: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_candidate_limit: number
          p_language?: string
          p_query_normalized: string
        }
        Returns: {
          chunk_id: string
          document_id: string
          match_kind: string
          similarity: number
          version_id: string
        }[]
      }
      retry_ingestion_job: {
        Args: { p_job_id: string }
        Returns: {
          attempt_count: number
          created_at: string
          detail: string
          document_id: string
          error_category: Database["app"]["Enums"]["job_error_category"]
          estimated_size_bytes: number
          heartbeat_at: string
          id: string
          idempotency_key: string
          job_kind: string
          last_error: string
          lease_expires_at: string
          lease_owner: string
          lease_token: string
          max_attempts: number
          next_attempt_at: string
          original_job_id: string
          payload_ref: Json
          priority: Database["app"]["Enums"]["job_priority"]
          status: Database["app"]["Enums"]["job_status"]
          updated_at: string
          version_id: string
        }[]
      }
      revoke_graph_entity_rule: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_payload: Json
          p_row_version: number
          p_rule_id: string
        }
        Returns: {
          entity_rules_generation: number
          invalidated: boolean
          rebuild_job_id: string
          repair_job_id: string
          row_version: number
          rule_id: string
          status: Database["app"]["Enums"]["graph_entity_rule_status"]
        }[]
      }
      revoke_session: {
        Args: { p_session_id: string; p_user_id: string }
        Returns: boolean
      }
      rollback_glossary_import: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          target_import_id: string
        }
        Returns: {
          alias_count: number
          entry_count: number
          import_id: string
          status: Database["app"]["Enums"]["glossary_import_status"]
        }[]
      }
      set_document_visibility: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_document_id: string
          p_visibility: Database["app"]["Enums"]["document_visibility"]
        }
        Returns: {
          created_at: string
          created_by: string | null
          current_version_id: string | null
          deleted_at: string | null
          description: string | null
          graph_eligible: boolean
          id: string
          title: string
          updated_at: string
          visibility: Database["app"]["Enums"]["document_visibility"]
          visibility_generation: number
        }
        SetofOptions: {
          from: "*"
          to: "documents"
          isOneToOne: true
          isSetofReturn: false
        }
      }
      transition_document_version_status: {
        Args: {
          p_expected_status: Database["app"]["Enums"]["document_status"]
          p_new_status: Database["app"]["Enums"]["document_status"]
          p_version_id: string
        }
        Returns: boolean
      }
      transition_graph_workspace_state: {
        Args: {
          p_from_states: Database["app"]["Enums"]["graph_workspace_state"][]
          p_snapshot?: Json
          p_to_state: Database["app"]["Enums"]["graph_workspace_state"]
          p_workspace_key: string
        }
        Returns: string
      }
      upsert_graph_entity_rule: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
          p_payload: Json
          p_row_version: number
          p_rule_id: string
        }
        Returns: {
          entity_rules_generation: number
          invalidated: boolean
          rebuild_job_id: string
          repair_job_id: string
          row_version: number
          rule_id: string
          status: Database["app"]["Enums"]["graph_entity_rule_status"]
        }[]
      }
      upsert_promotion_saga_intent: {
        Args: {
          p_destination_bucket: string
          p_destination_path: string
          p_expected_bytes: number
          p_expected_hash: string
          p_idempotency_key: string
          p_quarantine_bucket: string
          p_quarantine_path: string
          p_reservation_id?: string
          p_version_id: string
        }
        Returns: string
      }
      validate_active_graph_writer_lease: {
        Args: { p_owner: string; p_token: string }
        Returns: boolean
      }
      validate_active_lightrag_lease: {
        Args: { p_job_id: string; p_lease_token: string; p_owner: string }
        Returns: boolean
      }
      validate_caller_context: {
        Args: {
          caller_authorization_version: number
          caller_role: string
          caller_user_id: string
        }
        Returns: boolean
      }
      verify_audit_chain: { Args: { limit_n?: number }; Returns: string }
    }
    Enums: {
      approval_status: "pending" | "approved" | "rejected" | "revoked"
      bm25_job_operation: "upsert" | "delete"
      budget_reservation_status:
        | "reserved"
        | "committed"
        | "released"
        | "expired"
      document_status:
        | "uploading"
        | "uploaded"
        | "scanning"
        | "parsing"
        | "hybrid_ready"
        | "graph_pending"
        | "graph_ready"
        | "graph_ineligible"
        | "deletion_pending"
        | "failed"
      document_visibility: "company_visible" | "restricted"
      glossary_entry_type:
        | "product_code"
        | "project_name"
        | "acronym"
        | "canonical_term"
        | "identifier_rule"
      glossary_import_status:
        | "pending_approval"
        | "approved"
        | "rolled_back"
        | "rejected"
      graph_entity_rule_source: "admin" | "feedback" | "model"
      graph_entity_rule_status: "suggested" | "approved" | "revoked"
      graph_relation_label_policy: "directed" | "symmetric"
      graph_workspace_state:
        | "building"
        | "active"
        | "updating"
        | "filtered_dirty"
        | "quarantined"
        | "disabled"
        | "retired"
      job_error_category:
        | "transient"
        | "permanent"
        | "budget"
        | "authorization"
        | "validation"
        | "unknown"
      job_priority: "low" | "normal" | "high" | "critical"
      job_status:
        | "pending"
        | "processing"
        | "completed"
        | "failed"
        | "dead_letter"
        | "cancelled"
      lightrag_job_operation:
        | "index"
        | "remove"
        | "graph_acl_remove"
        | "rebuild"
      run_status:
        | "pending"
        | "running"
        | "completed"
        | "failed"
        | "cancelled"
        | "partial"
      scan_result:
        | "clean"
        | "infected"
        | "unscannable"
        | "stale_signature"
        | "over_limit"
        | "hash_mismatch"
      source_type: "file_upload" | "website_crawl"
      tool_permission_level: "none" | "read" | "execute" | "admin"
      user_role: "owner" | "admin" | "member" | "viewer"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  auth: {
    Tables: {
      audit_log_entries: {
        Row: {
          created_at: string | null
          id: string
          instance_id: string | null
          ip_address: string
          payload: Json | null
        }
        Insert: {
          created_at?: string | null
          id: string
          instance_id?: string | null
          ip_address?: string
          payload?: Json | null
        }
        Update: {
          created_at?: string | null
          id?: string
          instance_id?: string | null
          ip_address?: string
          payload?: Json | null
        }
        Relationships: []
      }
      custom_oauth_providers: {
        Row: {
          acceptable_client_ids: string[]
          attribute_mapping: Json
          authorization_params: Json
          authorization_url: string | null
          cached_discovery: Json | null
          client_id: string
          client_secret: string
          created_at: string
          custom_claims_allowlist: string[]
          discovery_cached_at: string | null
          discovery_url: string | null
          email_optional: boolean
          enabled: boolean
          id: string
          identifier: string
          issuer: string | null
          jwks_uri: string | null
          name: string
          pkce_enabled: boolean
          provider_type: string
          scopes: string[]
          skip_nonce_check: boolean
          token_url: string | null
          updated_at: string
          userinfo_url: string | null
        }
        Insert: {
          acceptable_client_ids?: string[]
          attribute_mapping?: Json
          authorization_params?: Json
          authorization_url?: string | null
          cached_discovery?: Json | null
          client_id: string
          client_secret: string
          created_at?: string
          custom_claims_allowlist?: string[]
          discovery_cached_at?: string | null
          discovery_url?: string | null
          email_optional?: boolean
          enabled?: boolean
          id?: string
          identifier: string
          issuer?: string | null
          jwks_uri?: string | null
          name: string
          pkce_enabled?: boolean
          provider_type: string
          scopes?: string[]
          skip_nonce_check?: boolean
          token_url?: string | null
          updated_at?: string
          userinfo_url?: string | null
        }
        Update: {
          acceptable_client_ids?: string[]
          attribute_mapping?: Json
          authorization_params?: Json
          authorization_url?: string | null
          cached_discovery?: Json | null
          client_id?: string
          client_secret?: string
          created_at?: string
          custom_claims_allowlist?: string[]
          discovery_cached_at?: string | null
          discovery_url?: string | null
          email_optional?: boolean
          enabled?: boolean
          id?: string
          identifier?: string
          issuer?: string | null
          jwks_uri?: string | null
          name?: string
          pkce_enabled?: boolean
          provider_type?: string
          scopes?: string[]
          skip_nonce_check?: boolean
          token_url?: string | null
          updated_at?: string
          userinfo_url?: string | null
        }
        Relationships: []
      }
      flow_state: {
        Row: {
          auth_code: string | null
          auth_code_issued_at: string | null
          authentication_method: string
          code_challenge: string | null
          code_challenge_method:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at: string | null
          email_optional: boolean
          id: string
          invite_token: string | null
          linking_target_id: string | null
          oauth_client_state_id: string | null
          provider_access_token: string | null
          provider_refresh_token: string | null
          provider_type: string
          referrer: string | null
          updated_at: string | null
          user_id: string | null
        }
        Insert: {
          auth_code?: string | null
          auth_code_issued_at?: string | null
          authentication_method: string
          code_challenge?: string | null
          code_challenge_method?:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at?: string | null
          email_optional?: boolean
          id: string
          invite_token?: string | null
          linking_target_id?: string | null
          oauth_client_state_id?: string | null
          provider_access_token?: string | null
          provider_refresh_token?: string | null
          provider_type: string
          referrer?: string | null
          updated_at?: string | null
          user_id?: string | null
        }
        Update: {
          auth_code?: string | null
          auth_code_issued_at?: string | null
          authentication_method?: string
          code_challenge?: string | null
          code_challenge_method?:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at?: string | null
          email_optional?: boolean
          id?: string
          invite_token?: string | null
          linking_target_id?: string | null
          oauth_client_state_id?: string | null
          provider_access_token?: string | null
          provider_refresh_token?: string | null
          provider_type?: string
          referrer?: string | null
          updated_at?: string | null
          user_id?: string | null
        }
        Relationships: []
      }
      identities: {
        Row: {
          created_at: string | null
          email: string | null
          id: string
          identity_data: Json
          last_sign_in_at: string | null
          provider: string
          provider_id: string
          updated_at: string | null
          user_id: string
        }
        Insert: {
          created_at?: string | null
          email?: string | null
          id?: string
          identity_data: Json
          last_sign_in_at?: string | null
          provider: string
          provider_id: string
          updated_at?: string | null
          user_id: string
        }
        Update: {
          created_at?: string | null
          email?: string | null
          id?: string
          identity_data?: Json
          last_sign_in_at?: string | null
          provider?: string
          provider_id?: string
          updated_at?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "identities_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      instances: {
        Row: {
          created_at: string | null
          id: string
          raw_base_config: string | null
          updated_at: string | null
          uuid: string | null
        }
        Insert: {
          created_at?: string | null
          id: string
          raw_base_config?: string | null
          updated_at?: string | null
          uuid?: string | null
        }
        Update: {
          created_at?: string | null
          id?: string
          raw_base_config?: string | null
          updated_at?: string | null
          uuid?: string | null
        }
        Relationships: []
      }
      mfa_amr_claims: {
        Row: {
          authentication_method: string
          created_at: string
          id: string
          session_id: string
          updated_at: string
        }
        Insert: {
          authentication_method: string
          created_at: string
          id: string
          session_id: string
          updated_at: string
        }
        Update: {
          authentication_method?: string
          created_at?: string
          id?: string
          session_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "mfa_amr_claims_session_id_fkey"
            columns: ["session_id"]
            isOneToOne: false
            referencedRelation: "sessions"
            referencedColumns: ["id"]
          },
        ]
      }
      mfa_challenges: {
        Row: {
          created_at: string
          factor_id: string
          id: string
          ip_address: unknown
          otp_code: string | null
          verified_at: string | null
          web_authn_session_data: Json | null
        }
        Insert: {
          created_at: string
          factor_id: string
          id: string
          ip_address: unknown
          otp_code?: string | null
          verified_at?: string | null
          web_authn_session_data?: Json | null
        }
        Update: {
          created_at?: string
          factor_id?: string
          id?: string
          ip_address?: unknown
          otp_code?: string | null
          verified_at?: string | null
          web_authn_session_data?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "mfa_challenges_auth_factor_id_fkey"
            columns: ["factor_id"]
            isOneToOne: false
            referencedRelation: "mfa_factors"
            referencedColumns: ["id"]
          },
        ]
      }
      mfa_factors: {
        Row: {
          created_at: string
          factor_type: Database["auth"]["Enums"]["factor_type"]
          friendly_name: string | null
          id: string
          last_challenged_at: string | null
          last_webauthn_challenge_data: Json | null
          phone: string | null
          secret: string | null
          status: Database["auth"]["Enums"]["factor_status"]
          updated_at: string
          user_id: string
          web_authn_aaguid: string | null
          web_authn_credential: Json | null
        }
        Insert: {
          created_at: string
          factor_type: Database["auth"]["Enums"]["factor_type"]
          friendly_name?: string | null
          id: string
          last_challenged_at?: string | null
          last_webauthn_challenge_data?: Json | null
          phone?: string | null
          secret?: string | null
          status: Database["auth"]["Enums"]["factor_status"]
          updated_at: string
          user_id: string
          web_authn_aaguid?: string | null
          web_authn_credential?: Json | null
        }
        Update: {
          created_at?: string
          factor_type?: Database["auth"]["Enums"]["factor_type"]
          friendly_name?: string | null
          id?: string
          last_challenged_at?: string | null
          last_webauthn_challenge_data?: Json | null
          phone?: string | null
          secret?: string | null
          status?: Database["auth"]["Enums"]["factor_status"]
          updated_at?: string
          user_id?: string
          web_authn_aaguid?: string | null
          web_authn_credential?: Json | null
        }
        Relationships: [
          {
            foreignKeyName: "mfa_factors_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      oauth_authorizations: {
        Row: {
          approved_at: string | null
          authorization_code: string | null
          authorization_id: string
          client_id: string
          code_challenge: string | null
          code_challenge_method:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at: string
          expires_at: string
          id: string
          nonce: string | null
          redirect_uri: string
          resource: string | null
          response_type: Database["auth"]["Enums"]["oauth_response_type"]
          scope: string
          state: string | null
          status: Database["auth"]["Enums"]["oauth_authorization_status"]
          user_id: string | null
        }
        Insert: {
          approved_at?: string | null
          authorization_code?: string | null
          authorization_id: string
          client_id: string
          code_challenge?: string | null
          code_challenge_method?:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at?: string
          expires_at?: string
          id: string
          nonce?: string | null
          redirect_uri: string
          resource?: string | null
          response_type?: Database["auth"]["Enums"]["oauth_response_type"]
          scope: string
          state?: string | null
          status?: Database["auth"]["Enums"]["oauth_authorization_status"]
          user_id?: string | null
        }
        Update: {
          approved_at?: string | null
          authorization_code?: string | null
          authorization_id?: string
          client_id?: string
          code_challenge?: string | null
          code_challenge_method?:
            | Database["auth"]["Enums"]["code_challenge_method"]
            | null
          created_at?: string
          expires_at?: string
          id?: string
          nonce?: string | null
          redirect_uri?: string
          resource?: string | null
          response_type?: Database["auth"]["Enums"]["oauth_response_type"]
          scope?: string
          state?: string | null
          status?: Database["auth"]["Enums"]["oauth_authorization_status"]
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "oauth_authorizations_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "oauth_clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "oauth_authorizations_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      oauth_client_states: {
        Row: {
          code_verifier: string | null
          created_at: string
          id: string
          provider_type: string
        }
        Insert: {
          code_verifier?: string | null
          created_at: string
          id: string
          provider_type: string
        }
        Update: {
          code_verifier?: string | null
          created_at?: string
          id?: string
          provider_type?: string
        }
        Relationships: []
      }
      oauth_clients: {
        Row: {
          client_name: string | null
          client_secret_hash: string | null
          client_type: Database["auth"]["Enums"]["oauth_client_type"]
          client_uri: string | null
          created_at: string
          deleted_at: string | null
          grant_types: string
          id: string
          logo_uri: string | null
          redirect_uris: string
          registration_type: Database["auth"]["Enums"]["oauth_registration_type"]
          token_endpoint_auth_method: string
          updated_at: string
        }
        Insert: {
          client_name?: string | null
          client_secret_hash?: string | null
          client_type?: Database["auth"]["Enums"]["oauth_client_type"]
          client_uri?: string | null
          created_at?: string
          deleted_at?: string | null
          grant_types: string
          id: string
          logo_uri?: string | null
          redirect_uris: string
          registration_type: Database["auth"]["Enums"]["oauth_registration_type"]
          token_endpoint_auth_method: string
          updated_at?: string
        }
        Update: {
          client_name?: string | null
          client_secret_hash?: string | null
          client_type?: Database["auth"]["Enums"]["oauth_client_type"]
          client_uri?: string | null
          created_at?: string
          deleted_at?: string | null
          grant_types?: string
          id?: string
          logo_uri?: string | null
          redirect_uris?: string
          registration_type?: Database["auth"]["Enums"]["oauth_registration_type"]
          token_endpoint_auth_method?: string
          updated_at?: string
        }
        Relationships: []
      }
      oauth_consents: {
        Row: {
          client_id: string
          granted_at: string
          id: string
          revoked_at: string | null
          scopes: string
          user_id: string
        }
        Insert: {
          client_id: string
          granted_at?: string
          id: string
          revoked_at?: string | null
          scopes: string
          user_id: string
        }
        Update: {
          client_id?: string
          granted_at?: string
          id?: string
          revoked_at?: string | null
          scopes?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "oauth_consents_client_id_fkey"
            columns: ["client_id"]
            isOneToOne: false
            referencedRelation: "oauth_clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "oauth_consents_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      one_time_tokens: {
        Row: {
          created_at: string
          id: string
          relates_to: string
          token_hash: string
          token_type: Database["auth"]["Enums"]["one_time_token_type"]
          updated_at: string
          user_id: string
        }
        Insert: {
          created_at?: string
          id: string
          relates_to: string
          token_hash: string
          token_type: Database["auth"]["Enums"]["one_time_token_type"]
          updated_at?: string
          user_id: string
        }
        Update: {
          created_at?: string
          id?: string
          relates_to?: string
          token_hash?: string
          token_type?: Database["auth"]["Enums"]["one_time_token_type"]
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "one_time_tokens_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      refresh_tokens: {
        Row: {
          created_at: string | null
          id: number
          instance_id: string | null
          parent: string | null
          revoked: boolean | null
          session_id: string | null
          token: string | null
          updated_at: string | null
          user_id: string | null
        }
        Insert: {
          created_at?: string | null
          id?: number
          instance_id?: string | null
          parent?: string | null
          revoked?: boolean | null
          session_id?: string | null
          token?: string | null
          updated_at?: string | null
          user_id?: string | null
        }
        Update: {
          created_at?: string | null
          id?: number
          instance_id?: string | null
          parent?: string | null
          revoked?: boolean | null
          session_id?: string | null
          token?: string | null
          updated_at?: string | null
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "refresh_tokens_session_id_fkey"
            columns: ["session_id"]
            isOneToOne: false
            referencedRelation: "sessions"
            referencedColumns: ["id"]
          },
        ]
      }
      saml_providers: {
        Row: {
          attribute_mapping: Json | null
          created_at: string | null
          entity_id: string
          id: string
          metadata_url: string | null
          metadata_xml: string
          name_id_format: string | null
          sso_provider_id: string
          updated_at: string | null
        }
        Insert: {
          attribute_mapping?: Json | null
          created_at?: string | null
          entity_id: string
          id: string
          metadata_url?: string | null
          metadata_xml: string
          name_id_format?: string | null
          sso_provider_id: string
          updated_at?: string | null
        }
        Update: {
          attribute_mapping?: Json | null
          created_at?: string | null
          entity_id?: string
          id?: string
          metadata_url?: string | null
          metadata_xml?: string
          name_id_format?: string | null
          sso_provider_id?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "saml_providers_sso_provider_id_fkey"
            columns: ["sso_provider_id"]
            isOneToOne: false
            referencedRelation: "sso_providers"
            referencedColumns: ["id"]
          },
        ]
      }
      saml_relay_states: {
        Row: {
          created_at: string | null
          flow_state_id: string | null
          for_email: string | null
          id: string
          redirect_to: string | null
          request_id: string
          sso_provider_id: string
          updated_at: string | null
        }
        Insert: {
          created_at?: string | null
          flow_state_id?: string | null
          for_email?: string | null
          id: string
          redirect_to?: string | null
          request_id: string
          sso_provider_id: string
          updated_at?: string | null
        }
        Update: {
          created_at?: string | null
          flow_state_id?: string | null
          for_email?: string | null
          id?: string
          redirect_to?: string | null
          request_id?: string
          sso_provider_id?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "saml_relay_states_flow_state_id_fkey"
            columns: ["flow_state_id"]
            isOneToOne: false
            referencedRelation: "flow_state"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "saml_relay_states_sso_provider_id_fkey"
            columns: ["sso_provider_id"]
            isOneToOne: false
            referencedRelation: "sso_providers"
            referencedColumns: ["id"]
          },
        ]
      }
      schema_migrations: {
        Row: {
          version: string
        }
        Insert: {
          version: string
        }
        Update: {
          version?: string
        }
        Relationships: []
      }
      sessions: {
        Row: {
          aal: Database["auth"]["Enums"]["aal_level"] | null
          created_at: string | null
          factor_id: string | null
          id: string
          ip: unknown
          not_after: string | null
          oauth_client_id: string | null
          refresh_token_counter: number | null
          refresh_token_hmac_key: string | null
          refreshed_at: string | null
          scopes: string | null
          tag: string | null
          updated_at: string | null
          user_agent: string | null
          user_id: string
        }
        Insert: {
          aal?: Database["auth"]["Enums"]["aal_level"] | null
          created_at?: string | null
          factor_id?: string | null
          id: string
          ip?: unknown
          not_after?: string | null
          oauth_client_id?: string | null
          refresh_token_counter?: number | null
          refresh_token_hmac_key?: string | null
          refreshed_at?: string | null
          scopes?: string | null
          tag?: string | null
          updated_at?: string | null
          user_agent?: string | null
          user_id: string
        }
        Update: {
          aal?: Database["auth"]["Enums"]["aal_level"] | null
          created_at?: string | null
          factor_id?: string | null
          id?: string
          ip?: unknown
          not_after?: string | null
          oauth_client_id?: string | null
          refresh_token_counter?: number | null
          refresh_token_hmac_key?: string | null
          refreshed_at?: string | null
          scopes?: string | null
          tag?: string | null
          updated_at?: string | null
          user_agent?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "sessions_oauth_client_id_fkey"
            columns: ["oauth_client_id"]
            isOneToOne: false
            referencedRelation: "oauth_clients"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "sessions_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      sso_domains: {
        Row: {
          created_at: string | null
          domain: string
          id: string
          sso_provider_id: string
          updated_at: string | null
        }
        Insert: {
          created_at?: string | null
          domain: string
          id: string
          sso_provider_id: string
          updated_at?: string | null
        }
        Update: {
          created_at?: string | null
          domain?: string
          id?: string
          sso_provider_id?: string
          updated_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "sso_domains_sso_provider_id_fkey"
            columns: ["sso_provider_id"]
            isOneToOne: false
            referencedRelation: "sso_providers"
            referencedColumns: ["id"]
          },
        ]
      }
      sso_providers: {
        Row: {
          created_at: string | null
          disabled: boolean | null
          id: string
          resource_id: string | null
          updated_at: string | null
        }
        Insert: {
          created_at?: string | null
          disabled?: boolean | null
          id: string
          resource_id?: string | null
          updated_at?: string | null
        }
        Update: {
          created_at?: string | null
          disabled?: boolean | null
          id?: string
          resource_id?: string | null
          updated_at?: string | null
        }
        Relationships: []
      }
      users: {
        Row: {
          aud: string | null
          banned_until: string | null
          confirmation_sent_at: string | null
          confirmation_token: string | null
          confirmed_at: string | null
          created_at: string | null
          deleted_at: string | null
          email: string | null
          email_change: string | null
          email_change_confirm_status: number | null
          email_change_sent_at: string | null
          email_change_token_current: string | null
          email_change_token_new: string | null
          email_confirmed_at: string | null
          encrypted_password: string | null
          id: string
          instance_id: string | null
          invited_at: string | null
          is_anonymous: boolean
          is_sso_user: boolean
          is_super_admin: boolean | null
          last_sign_in_at: string | null
          phone: string | null
          phone_change: string | null
          phone_change_sent_at: string | null
          phone_change_token: string | null
          phone_confirmed_at: string | null
          raw_app_meta_data: Json | null
          raw_user_meta_data: Json | null
          reauthentication_sent_at: string | null
          reauthentication_token: string | null
          recovery_sent_at: string | null
          recovery_token: string | null
          role: string | null
          updated_at: string | null
        }
        Insert: {
          aud?: string | null
          banned_until?: string | null
          confirmation_sent_at?: string | null
          confirmation_token?: string | null
          confirmed_at?: string | null
          created_at?: string | null
          deleted_at?: string | null
          email?: string | null
          email_change?: string | null
          email_change_confirm_status?: number | null
          email_change_sent_at?: string | null
          email_change_token_current?: string | null
          email_change_token_new?: string | null
          email_confirmed_at?: string | null
          encrypted_password?: string | null
          id: string
          instance_id?: string | null
          invited_at?: string | null
          is_anonymous?: boolean
          is_sso_user?: boolean
          is_super_admin?: boolean | null
          last_sign_in_at?: string | null
          phone?: string | null
          phone_change?: string | null
          phone_change_sent_at?: string | null
          phone_change_token?: string | null
          phone_confirmed_at?: string | null
          raw_app_meta_data?: Json | null
          raw_user_meta_data?: Json | null
          reauthentication_sent_at?: string | null
          reauthentication_token?: string | null
          recovery_sent_at?: string | null
          recovery_token?: string | null
          role?: string | null
          updated_at?: string | null
        }
        Update: {
          aud?: string | null
          banned_until?: string | null
          confirmation_sent_at?: string | null
          confirmation_token?: string | null
          confirmed_at?: string | null
          created_at?: string | null
          deleted_at?: string | null
          email?: string | null
          email_change?: string | null
          email_change_confirm_status?: number | null
          email_change_sent_at?: string | null
          email_change_token_current?: string | null
          email_change_token_new?: string | null
          email_confirmed_at?: string | null
          encrypted_password?: string | null
          id?: string
          instance_id?: string | null
          invited_at?: string | null
          is_anonymous?: boolean
          is_sso_user?: boolean
          is_super_admin?: boolean | null
          last_sign_in_at?: string | null
          phone?: string | null
          phone_change?: string | null
          phone_change_sent_at?: string | null
          phone_change_token?: string | null
          phone_confirmed_at?: string | null
          raw_app_meta_data?: Json | null
          raw_user_meta_data?: Json | null
          reauthentication_sent_at?: string | null
          reauthentication_token?: string | null
          recovery_sent_at?: string | null
          recovery_token?: string | null
          role?: string | null
          updated_at?: string | null
        }
        Relationships: []
      }
      webauthn_challenges: {
        Row: {
          challenge_type: string
          created_at: string
          expires_at: string
          id: string
          session_data: Json
          user_id: string | null
        }
        Insert: {
          challenge_type: string
          created_at?: string
          expires_at: string
          id?: string
          session_data: Json
          user_id?: string | null
        }
        Update: {
          challenge_type?: string
          created_at?: string
          expires_at?: string
          id?: string
          session_data?: Json
          user_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "webauthn_challenges_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      webauthn_credentials: {
        Row: {
          aaguid: string | null
          attestation_type: string
          backed_up: boolean
          backup_eligible: boolean
          created_at: string
          credential_id: string
          friendly_name: string
          id: string
          last_used_at: string | null
          public_key: string
          sign_count: number
          transports: Json
          updated_at: string
          user_id: string
        }
        Insert: {
          aaguid?: string | null
          attestation_type?: string
          backed_up?: boolean
          backup_eligible?: boolean
          created_at?: string
          credential_id: string
          friendly_name?: string
          id?: string
          last_used_at?: string | null
          public_key: string
          sign_count?: number
          transports?: Json
          updated_at?: string
          user_id: string
        }
        Update: {
          aaguid?: string | null
          attestation_type?: string
          backed_up?: boolean
          backup_eligible?: boolean
          created_at?: string
          credential_id?: string
          friendly_name?: string
          id?: string
          last_used_at?: string | null
          public_key?: string
          sign_count?: number
          transports?: Json
          updated_at?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "webauthn_credentials_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      email: { Args: never; Returns: string }
      jwt: { Args: never; Returns: Json }
      role: { Args: never; Returns: string }
      uid: { Args: never; Returns: string }
    }
    Enums: {
      aal_level: "aal1" | "aal2" | "aal3"
      code_challenge_method: "s256" | "plain"
      factor_status: "unverified" | "verified"
      factor_type: "totp" | "webauthn" | "phone"
      oauth_authorization_status: "pending" | "approved" | "denied" | "expired"
      oauth_client_type: "public" | "confidential"
      oauth_registration_type: "dynamic" | "manual"
      oauth_response_type: "code"
      one_time_token_type:
        | "confirmation_token"
        | "reauthentication_token"
        | "recovery_token"
        | "email_change_token_new"
        | "email_change_token_current"
        | "phone_change_token"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  storage: {
    Tables: {
      buckets: {
        Row: {
          allowed_mime_types: string[] | null
          avif_autodetection: boolean | null
          created_at: string | null
          file_size_limit: number | null
          id: string
          name: string
          owner: string | null
          owner_id: string | null
          public: boolean | null
          type: Database["storage"]["Enums"]["buckettype"]
          updated_at: string | null
        }
        Insert: {
          allowed_mime_types?: string[] | null
          avif_autodetection?: boolean | null
          created_at?: string | null
          file_size_limit?: number | null
          id: string
          name: string
          owner?: string | null
          owner_id?: string | null
          public?: boolean | null
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string | null
        }
        Update: {
          allowed_mime_types?: string[] | null
          avif_autodetection?: boolean | null
          created_at?: string | null
          file_size_limit?: number | null
          id?: string
          name?: string
          owner?: string | null
          owner_id?: string | null
          public?: boolean | null
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string | null
        }
        Relationships: []
      }
      buckets_analytics: {
        Row: {
          created_at: string
          deleted_at: string | null
          format: string
          id: string
          name: string
          type: Database["storage"]["Enums"]["buckettype"]
          updated_at: string
        }
        Insert: {
          created_at?: string
          deleted_at?: string | null
          format?: string
          id?: string
          name: string
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string
        }
        Update: {
          created_at?: string
          deleted_at?: string | null
          format?: string
          id?: string
          name?: string
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string
        }
        Relationships: []
      }
      buckets_vectors: {
        Row: {
          created_at: string
          id: string
          type: Database["storage"]["Enums"]["buckettype"]
          updated_at: string
        }
        Insert: {
          created_at?: string
          id: string
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string
        }
        Update: {
          created_at?: string
          id?: string
          type?: Database["storage"]["Enums"]["buckettype"]
          updated_at?: string
        }
        Relationships: []
      }
      iceberg_namespaces: {
        Row: {
          bucket_name: string
          catalog_id: string
          created_at: string
          id: string
          metadata: Json
          name: string
          updated_at: string
        }
        Insert: {
          bucket_name: string
          catalog_id: string
          created_at?: string
          id?: string
          metadata?: Json
          name: string
          updated_at?: string
        }
        Update: {
          bucket_name?: string
          catalog_id?: string
          created_at?: string
          id?: string
          metadata?: Json
          name?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "iceberg_namespaces_catalog_id_fkey"
            columns: ["catalog_id"]
            isOneToOne: false
            referencedRelation: "buckets_analytics"
            referencedColumns: ["id"]
          },
        ]
      }
      iceberg_tables: {
        Row: {
          bucket_name: string
          catalog_id: string
          created_at: string
          id: string
          location: string
          name: string
          namespace_id: string
          remote_table_id: string | null
          shard_id: string | null
          shard_key: string | null
          updated_at: string
        }
        Insert: {
          bucket_name: string
          catalog_id: string
          created_at?: string
          id?: string
          location: string
          name: string
          namespace_id: string
          remote_table_id?: string | null
          shard_id?: string | null
          shard_key?: string | null
          updated_at?: string
        }
        Update: {
          bucket_name?: string
          catalog_id?: string
          created_at?: string
          id?: string
          location?: string
          name?: string
          namespace_id?: string
          remote_table_id?: string | null
          shard_id?: string | null
          shard_key?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "iceberg_tables_catalog_id_fkey"
            columns: ["catalog_id"]
            isOneToOne: false
            referencedRelation: "buckets_analytics"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "iceberg_tables_namespace_id_fkey"
            columns: ["namespace_id"]
            isOneToOne: false
            referencedRelation: "iceberg_namespaces"
            referencedColumns: ["id"]
          },
        ]
      }
      migrations: {
        Row: {
          executed_at: string | null
          hash: string
          id: number
          name: string
        }
        Insert: {
          executed_at?: string | null
          hash: string
          id: number
          name: string
        }
        Update: {
          executed_at?: string | null
          hash?: string
          id?: number
          name?: string
        }
        Relationships: []
      }
      objects: {
        Row: {
          bucket_id: string | null
          created_at: string | null
          id: string
          last_accessed_at: string | null
          metadata: Json | null
          name: string | null
          owner: string | null
          owner_id: string | null
          path_tokens: string[] | null
          updated_at: string | null
          user_metadata: Json | null
          version: string | null
        }
        Insert: {
          bucket_id?: string | null
          created_at?: string | null
          id?: string
          last_accessed_at?: string | null
          metadata?: Json | null
          name?: string | null
          owner?: string | null
          owner_id?: string | null
          path_tokens?: string[] | null
          updated_at?: string | null
          user_metadata?: Json | null
          version?: string | null
        }
        Update: {
          bucket_id?: string | null
          created_at?: string | null
          id?: string
          last_accessed_at?: string | null
          metadata?: Json | null
          name?: string | null
          owner?: string | null
          owner_id?: string | null
          path_tokens?: string[] | null
          updated_at?: string | null
          user_metadata?: Json | null
          version?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "objects_bucketId_fkey"
            columns: ["bucket_id"]
            isOneToOne: false
            referencedRelation: "buckets"
            referencedColumns: ["id"]
          },
        ]
      }
      s3_multipart_uploads: {
        Row: {
          bucket_id: string
          created_at: string
          id: string
          in_progress_size: number
          key: string
          metadata: Json | null
          owner_id: string | null
          upload_signature: string
          user_metadata: Json | null
          version: string
        }
        Insert: {
          bucket_id: string
          created_at?: string
          id: string
          in_progress_size?: number
          key: string
          metadata?: Json | null
          owner_id?: string | null
          upload_signature: string
          user_metadata?: Json | null
          version: string
        }
        Update: {
          bucket_id?: string
          created_at?: string
          id?: string
          in_progress_size?: number
          key?: string
          metadata?: Json | null
          owner_id?: string | null
          upload_signature?: string
          user_metadata?: Json | null
          version?: string
        }
        Relationships: [
          {
            foreignKeyName: "s3_multipart_uploads_bucket_id_fkey"
            columns: ["bucket_id"]
            isOneToOne: false
            referencedRelation: "buckets"
            referencedColumns: ["id"]
          },
        ]
      }
      s3_multipart_uploads_parts: {
        Row: {
          bucket_id: string
          created_at: string
          etag: string
          id: string
          key: string
          owner_id: string | null
          part_number: number
          size: number
          upload_id: string
          version: string
        }
        Insert: {
          bucket_id: string
          created_at?: string
          etag: string
          id?: string
          key: string
          owner_id?: string | null
          part_number: number
          size?: number
          upload_id: string
          version: string
        }
        Update: {
          bucket_id?: string
          created_at?: string
          etag?: string
          id?: string
          key?: string
          owner_id?: string | null
          part_number?: number
          size?: number
          upload_id?: string
          version?: string
        }
        Relationships: [
          {
            foreignKeyName: "s3_multipart_uploads_parts_bucket_id_fkey"
            columns: ["bucket_id"]
            isOneToOne: false
            referencedRelation: "buckets"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "s3_multipart_uploads_parts_upload_id_fkey"
            columns: ["upload_id"]
            isOneToOne: false
            referencedRelation: "s3_multipart_uploads"
            referencedColumns: ["id"]
          },
        ]
      }
      vector_indexes: {
        Row: {
          bucket_id: string
          created_at: string
          data_type: string
          dimension: number
          distance_metric: string
          id: string
          metadata_configuration: Json | null
          name: string
          updated_at: string
        }
        Insert: {
          bucket_id: string
          created_at?: string
          data_type: string
          dimension: number
          distance_metric: string
          id?: string
          metadata_configuration?: Json | null
          name: string
          updated_at?: string
        }
        Update: {
          bucket_id?: string
          created_at?: string
          data_type?: string
          dimension?: number
          distance_metric?: string
          id?: string
          metadata_configuration?: Json | null
          name?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "vector_indexes_bucket_id_fkey"
            columns: ["bucket_id"]
            isOneToOne: false
            referencedRelation: "buckets_vectors"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      allow_any_operation: {
        Args: { expected_operations: string[] }
        Returns: boolean
      }
      allow_only_operation: {
        Args: { expected_operation: string }
        Returns: boolean
      }
      can_insert_object: {
        Args: { bucketid: string; metadata: Json; name: string; owner: string }
        Returns: undefined
      }
      extension: { Args: { name: string }; Returns: string }
      filename: { Args: { name: string }; Returns: string }
      foldername: { Args: { name: string }; Returns: string[] }
      get_common_prefix: {
        Args: { p_delimiter: string; p_key: string; p_prefix: string }
        Returns: string
      }
      get_size_by_bucket: {
        Args: never
        Returns: {
          bucket_id: string
          size: number
        }[]
      }
      list_multipart_uploads_with_delimiter: {
        Args: {
          bucket_id: string
          delimiter_param: string
          max_keys?: number
          next_key_token?: string
          next_upload_token?: string
          prefix_param: string
        }
        Returns: {
          created_at: string
          id: string
          key: string
        }[]
      }
      list_objects_with_delimiter: {
        Args: {
          _bucket_id: string
          delimiter_param: string
          max_keys?: number
          next_token?: string
          prefix_param: string
          sort_order?: string
          start_after?: string
        }
        Returns: {
          created_at: string
          id: string
          last_accessed_at: string
          metadata: Json
          name: string
          updated_at: string
        }[]
      }
      operation: { Args: never; Returns: string }
      search: {
        Args: {
          bucketname: string
          levels?: number
          limits?: number
          offsets?: number
          prefix: string
          search?: string
          sortcolumn?: string
          sortorder?: string
        }
        Returns: {
          created_at: string
          id: string
          last_accessed_at: string
          metadata: Json
          name: string
          updated_at: string
        }[]
      }
      search_by_timestamp: {
        Args: {
          p_bucket_id: string
          p_level: number
          p_limit: number
          p_prefix: string
          p_sort_column: string
          p_sort_column_after: string
          p_sort_order: string
          p_start_after: string
        }
        Returns: {
          created_at: string
          id: string
          key: string
          last_accessed_at: string
          metadata: Json
          name: string
          updated_at: string
        }[]
      }
      search_v2: {
        Args: {
          bucket_name: string
          levels?: number
          limits?: number
          prefix: string
          sort_column?: string
          sort_column_after?: string
          sort_order?: string
          start_after?: string
        }
        Returns: {
          created_at: string
          id: string
          key: string
          last_accessed_at: string
          metadata: Json
          name: string
          updated_at: string
        }[]
      }
    }
    Enums: {
      buckettype: "STANDARD" | "ANALYTICS" | "VECTOR"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  app: {
    Enums: {
      approval_status: ["pending", "approved", "rejected", "revoked"],
      bm25_job_operation: ["upsert", "delete"],
      budget_reservation_status: [
        "reserved",
        "committed",
        "released",
        "expired",
      ],
      document_status: [
        "uploading",
        "uploaded",
        "scanning",
        "parsing",
        "hybrid_ready",
        "graph_pending",
        "graph_ready",
        "graph_ineligible",
        "deletion_pending",
        "failed",
      ],
      document_visibility: ["company_visible", "restricted"],
      glossary_entry_type: [
        "product_code",
        "project_name",
        "acronym",
        "canonical_term",
        "identifier_rule",
      ],
      glossary_import_status: [
        "pending_approval",
        "approved",
        "rolled_back",
        "rejected",
      ],
      graph_entity_rule_source: ["admin", "feedback", "model"],
      graph_entity_rule_status: ["suggested", "approved", "revoked"],
      graph_relation_label_policy: ["directed", "symmetric"],
      graph_workspace_state: [
        "building",
        "active",
        "updating",
        "filtered_dirty",
        "quarantined",
        "disabled",
        "retired",
      ],
      job_error_category: [
        "transient",
        "permanent",
        "budget",
        "authorization",
        "validation",
        "unknown",
      ],
      job_priority: ["low", "normal", "high", "critical"],
      job_status: [
        "pending",
        "processing",
        "completed",
        "failed",
        "dead_letter",
        "cancelled",
      ],
      lightrag_job_operation: [
        "index",
        "remove",
        "graph_acl_remove",
        "rebuild",
      ],
      run_status: [
        "pending",
        "running",
        "completed",
        "failed",
        "cancelled",
        "partial",
      ],
      scan_result: [
        "clean",
        "infected",
        "unscannable",
        "stale_signature",
        "over_limit",
        "hash_mismatch",
      ],
      source_type: ["file_upload", "website_crawl"],
      tool_permission_level: ["none", "read", "execute", "admin"],
      user_role: ["owner", "admin", "member", "viewer"],
    },
  },
  auth: {
    Enums: {
      aal_level: ["aal1", "aal2", "aal3"],
      code_challenge_method: ["s256", "plain"],
      factor_status: ["unverified", "verified"],
      factor_type: ["totp", "webauthn", "phone"],
      oauth_authorization_status: ["pending", "approved", "denied", "expired"],
      oauth_client_type: ["public", "confidential"],
      oauth_registration_type: ["dynamic", "manual"],
      oauth_response_type: ["code"],
      one_time_token_type: [
        "confirmation_token",
        "reauthentication_token",
        "recovery_token",
        "email_change_token_new",
        "email_change_token_current",
        "phone_change_token",
      ],
    },
  },
  public: {
    Enums: {},
  },
  storage: {
    Enums: {
      buckettype: ["STANDARD", "ANALYTICS", "VECTOR"],
    },
  },
} as const


"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { tvDisplayApi } from "@/features/tv-display/api/tv-display-api";
import type {
  CreateAnnouncementInput,
  CreateTvDisplayInput,
  CreateTvInfoContentInput,
  UpdateTvDisplayInput,
  UpdateTvInfoContentInput,
} from "@/features/tv-display/types";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api-client";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export const tvDisplayKeys = {
  all: ["tv-displays"] as const,
  list: () => ["tv-displays", "list"] as const,
  detail: (id: string) => ["tv-displays", "detail", id] as const,
  announcements: (id: string) => ["tv-displays", "announcements", id] as const,
  preview: (id: string) => ["tv-displays", "preview", id] as const,
  infoContent: () => ["tv-displays", "info-content"] as const,
};

export function useTvDisplays() {
  return useQuery({ queryKey: tvDisplayKeys.list(), queryFn: () => tvDisplayApi.list() });
}

export function useTvDisplayPreview(id: string | null) {
  return useQuery({
    queryKey: tvDisplayKeys.preview(id ?? ""),
    queryFn: () => tvDisplayApi.preview(id as string),
    enabled: Boolean(id),
    refetchInterval: 15_000,
  });
}

export function useCreateTvDisplay() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: CreateTvDisplayInput) => tvDisplayApi.create(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.all });
      toast({ title: "TV display created", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not create TV display", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useUpdateTvDisplay(id: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: UpdateTvDisplayInput) => tvDisplayApi.update(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.all });
      toast({ title: "TV display updated", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not update TV display", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useDeleteTvDisplay() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => tvDisplayApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.all });
      toast({ title: "TV display deleted", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not delete TV display", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useAnnouncements(configId: string | null) {
  return useQuery({
    queryKey: tvDisplayKeys.announcements(configId ?? ""),
    queryFn: () => tvDisplayApi.listAnnouncements(configId as string),
    enabled: Boolean(configId),
  });
}

export function useCreateAnnouncement(configId: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: CreateAnnouncementInput) => tvDisplayApi.createAnnouncement(configId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.announcements(configId) });
      toast({ title: "Announcement added", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not add announcement", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useToggleAnnouncement(configId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      tvDisplayApi.updateAnnouncement(id, { isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.announcements(configId) });
    },
  });
}

export function useDeleteAnnouncement(configId: string) {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => tvDisplayApi.deleteAnnouncement(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.announcements(configId) });
      toast({ title: "Announcement deleted", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not delete announcement", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useInfoContent() {
  return useQuery({ queryKey: tvDisplayKeys.infoContent(), queryFn: () => tvDisplayApi.listInfoContent() });
}

export function useCreateInfoContent() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (input: CreateTvInfoContentInput) => tvDisplayApi.createInfoContent(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.infoContent() });
      toast({ title: "Information content added", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not add content", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useUpdateInfoContent() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: UpdateTvInfoContentInput }) =>
      tvDisplayApi.updateInfoContent(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.infoContent() });
      toast({ title: "Content updated", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not update content", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useDeleteInfoContent() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => tvDisplayApi.deleteInfoContent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.infoContent() });
      toast({ title: "Content deleted", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not delete content", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

export function useUploadInfoContentImage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => tvDisplayApi.uploadInfoContentImage(id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.infoContent() });
      toast({ title: "Photo uploaded", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not upload photo", description: error instanceof Error ? error.message : "Please try again.", variant: "error" });
    },
  });
}

export function useDeleteInfoContentImage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (id: string) => tvDisplayApi.deleteInfoContentImage(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: tvDisplayKeys.infoContent() });
      toast({ title: "Photo removed", variant: "success" });
    },
    onError: (error) => {
      toast({ title: "Could not remove photo", description: errorMessage(error, "Please try again."), variant: "error" });
    },
  });
}

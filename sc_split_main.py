"""
Reference free AF-based demultiplexing on pooled scRNA-seq (state intialisation using pca, with random factor to avoid local maximum)
Jon Xu (jun.xu@uq.edu.au)
Lachlan Coin
Aug 2018
"""

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import datetime
import csv

class models:
    def __init__(self, base_calls_mtx, num):
        """
        Model class containing SNVs, matrices counts, barcodes, model allele fraction with assigned cells

        Parameters:
             base_calls_mtx(list of Dataframes): SNV-barcode matrix containing lists of base calls
             all_POS(list): list of SNVs positions
             barcodes(list): list of cell barcodes
             num(int): number of total samples
             P_s_c(DataFrame): barcode/sample matrix containing the probability of seeing sample s with observation of barcode c
             lP_c_s(DataFrame): barcode/sample matrix containing the log likelihood of seeing barcode c under sample s, whose sum should increase by each iteration
             assigned(list): final lists of cell/barcode assigned to each cluster/model
             model_af(Dataframe): Dataframe of model allele frequencies P(A) for each SNV and state
        """
        self.ref_bc_mtx = base_calls_mtx[0]
        self.alt_bc_mtx = base_calls_mtx[1]
        self.all_POS = base_calls_mtx[2].tolist()
        self.barcodes = base_calls_mtx[3].tolist()
        self.num = num + 1  # including an additional background state for doublets
        self.P_s_c = pd.DataFrame(0, index = self.barcodes, columns = range(self.num))
        self.lP_c_s = pd.DataFrame(0, index = self.barcodes, columns = range(self.num))
        self.assigned = []
        for _ in range(self.num):
            self.assigned.append([])
        self.model_af = pd.DataFrame(0, index=self.all_POS, columns=range(self.num))
        self.pseudo = 1

        # set background alt count proportion as allele fraction for each SNVs of doublet state, with pseudo count added for 0 counts on multi-base SNPs
        N_A = self.alt_bc_mtx.sum(axis=1) + self.pseudo
        N_R = self.ref_bc_mtx.sum(axis=1) + self.pseudo
        N_T = N_A + N_R
        k_ref = N_R / N_T
        k_alt = N_A / N_T

        # find barcodes for state initialisation, using subsetting/PCA/K-mean
        base_mtx = (self.alt_bc_mtx + self.ref_bc_mtx).toarray()
        rows = [*range(base_mtx.shape[0])]
        cols = [*range(base_mtx.shape[1])]
        irows = np.array(rows)
        icols = np.array(cols)
        nrows = len(rows)
        ncols = len(cols)
        mrows = mcols = 0
        while (mrows < (0.9 * nrows)) or (mcols < (0.9 * ncols)):
            rbrows = np.sort(np.unique(list(map(int, np.random.beta(1,10,int(0.1*nrows))*nrows))))    # id of random 10% bottom rows
            rbcols = np.sort(np.unique(list(map(int, np.random.beta(1,10,int(0.1*ncols))*ncols))))    # id of random 10% bottom cols
            rows = np.count_nonzero(base_mtx, axis=1).argsort().tolist()    # sorted row index according to non_zero counts across cols in the current matrix
            cols = np.count_nonzero(base_mtx, axis=0).argsort().tolist()    # sorted col index according to non_zero counts across rows in the current matrix
            for item in rbrows:
                rows.remove(item)   # remove the randomly picked least non_zero rows
            for item in rbcols:
                cols.remove(item)   # remove the randomly picked least non_zero cols
            irows = irows[rows]     # record the index of the remaining rows according to original matrix
            icols = icols[cols]     # record the index of the remaining cols according to original matrix
            nrows = len(rows)
            ncols = len(cols)
            base_mtx = base_mtx[rows][:,cols]
            mrows = min(np.count_nonzero(base_mtx, axis=0))     # minimum non-zero rows in all cols
            mcols = min(np.count_nonzero(base_mtx, axis=1))     # minimum non-zero cols in all rows
        alt_subset = self.alt_bc_mtx[irows][:, icols].todense()
        ref_subset = self.ref_bc_mtx[irows][:, icols].todense()
        alt_prop = (alt_subset + 0.01) / (alt_subset + ref_subset + 0.02)
        alt_pca = StandardScaler().fit_transform(alt_prop.T)
        pca = PCA(n_components=20)
        pca_alt = pca.fit_transform(alt_pca)
        kmeans = KMeans(n_clusters=self.num, random_state=0).fit(pca_alt)

        # intialise allele frequency for model states
        self.initial = []
        for n in range(self.num):
            self.initial.append([])
            for index, col in enumerate(icols):
                if kmeans.labels_[index] == n:
                    self.initial[n].append(self.barcodes[col])
            barcode_alt = np.array(self.alt_bc_mtx[:, icols[kmeans.labels_==n]].sum(axis=1))
            barcode_ref = np.array(self.ref_bc_mtx[:, icols[kmeans.labels_==n]].sum(axis=1))
            self.model_af.loc[:, n] = (barcode_alt + k_alt) / (barcode_alt + barcode_ref + k_alt + k_ref)


    def run_EM(self):

        # commencing E-M
        iterations = 0
        self.sum_log_likelihood = [1,2]  # dummy likelihood as a start
        while self.sum_log_likelihood[-2] != self.sum_log_likelihood[-1]:
            iterations += 1
            progress = 'Iteration ' + str(iterations) + '   ' + str(datetime.datetime.now()) + '\n'
            with open('sc_split.log', 'a') as myfile: myfile.write(progress)
            self.calculate_cell_likelihood()  # E-step, calculate the expected cell origin likelihood with a function of self.model_af (theta)
            self.calculate_model_af()  # M-step, to optimise unknown model parameter self.model_af (theta)
            # approximation due to python calculation limit
            self.sum_log_likelihood.append(self.lP_c_s.max(axis=1).sum())  # L = Prod_c[Sum_s(P(c|s))], thus LL = Sum_c{log[Sum_s(P(c|s))]}
            # self.sum_log_likelihood.append(((2**self.lP_c_s).sum(axis=1)+1e-323).apply(np.log2).sum())


    def calculate_cell_likelihood(self):
        """
        Calculate cell|sample likelihood P(c|s) and derive sample|cell probability P(s|c)
        P(c|s_v) = P(N(A),N(R)|s) = P(g_A|s)^N(A) * (1-P(g_A|s))^N(R)
        log(P(c|s)) = sum_v{(N(A)_c,v*log(P(g_A|s)) + N(R)_c,v*log(1-P(g_A|s)))}
        P(s_n|c) = P(c|s_n) / [P(c|s_1) + P(c|s_2) + ... + P(c|s_n)]
        log(P(s1|c) = log{1/[1+P(c|s2)/P(c|s1)]} = -log[1+P(c|s2)/P(c|s1)] = -log[1+2^(logP(c|s2)-logP(c|s1))]
        """

        # calculate likelihood P(c|s) based on allele probability
        for n in range(self.num):
            matcalc = self.alt_bc_mtx.T.multiply(self.model_af.loc[:, n].apply(np.log2)).T \
                    + self.ref_bc_mtx.T.multiply((1 - self.model_af.loc[:, n]).apply(np.log2)).T
            self.lP_c_s.loc[:, n] = matcalc.sum(axis=0).tolist()[0]  # log likelihood to avoid python computation limit of 1e-323/1e+308

        # transform to cell sample probability using Baysian rule
        for i in range(self.num):
            denom = 0
            for j in range(self.num):
                denom += 2 ** (self.lP_c_s.loc[:, j] - self.lP_c_s.loc[:, i])
            self.P_s_c.loc[:, i] = 1 / denom


    def calculate_model_af(self):
        """
        Update the model allele fraction by distributing the alt and total counts of each barcode on a certain snv to the model based on P(s|c)
        """

        N_ref = self.ref_bc_mtx.sum(axis=1) + self.pseudo
        N_alt = self.alt_bc_mtx.sum(axis=1) + self.pseudo
        k_ref = N_ref / (N_ref + N_alt)
        k_alt = N_alt / (N_ref + N_alt)
        self.model_af = pd.DataFrame((self.alt_bc_mtx.dot(self.P_s_c) + k_alt) / ((self.alt_bc_mtx + self.ref_bc_mtx).dot(self.P_s_c) + k_ref + k_alt),
                                        index = self.all_POS, columns = range(self.num))


    def assign_cells(self):
        """
            Final assignment of cells according to P(s|c) >= 0.9
        """

        for n in range(self.num):
            self.assigned[n] = sorted(self.P_s_c.loc[self.P_s_c[n] >= 0.9].index.values.tolist())


    def define_doublet(self):
        """
            Locate the doublet state
        """

        max_avg_entropy = 0
        for n in range(self.num):
            index = []
            # transform barcode assignments to indices
            for item in self.assigned[n]:
                index.append(self.barcodes.index(item))
            # locate informative SNVs for the state
            reads = (self.alt_bc_mtx + self.ref_bc_mtx)[:, index].sum(axis=1)
            subset = self.model_af[reads > 10][n]
            entropy = -subset * np.log2(subset + 1e-20) - (1 - subset) * np.log2(1 - subset + 1e-20)
            avg_entropy = np.average(entropy)
            if avg_entropy > max_avg_entropy:
                self.doublet = n
                max_avg_entropy = avg_entropy


def main():

    num_models = 7          # number of models in each run

    # input and output files
    ref_csv = 'ref_filtered.csv'  # reference matrix
    alt_csv = 'alt_filtered.csv'  # alternative matrix

    progress = 'Starting data collection: ' + str(datetime.datetime.now()) + '\n'
    with open('sc_split.log', 'a') as myfile: myfile.write(progress)

    # Read in existing matrix from the csv files
    ref = pd.read_csv(ref_csv, header=0, index_col=0)  # read ref matrix with header line and column
    alt = pd.read_csv(alt_csv, header=0, index_col=0)  # read alt matrix with header line and column
    ref_s = csr_matrix(ref.values)
    alt_s = csr_matrix(alt.values)
    base_calls_mtx = [ref_s, alt_s, ref.index, ref.columns]
    progress = 'AF matrices uploaded: ' + str(datetime.datetime.now()) + '\n'
    with open('sc_split.log', 'a') as myfile: myfile.write(progress)

    max_likelihood = -1e10
    for i in range(50):
        with open('sc_split.log', 'a') as myfile: myfile.write('round ' + str(i) + '\n')
        model = models(base_calls_mtx, num_models)  # model initialisation
        model.run_EM()  # model training
        model.assign_cells()    # assign cells to states
        if model.sum_log_likelihood[-1] > max_likelihood:
            max_likelihood = model.sum_log_likelihood[-1]
            initial = model.initial
            assigned = model.assigned
    model.assigned = assigned
    model.initial = initial
    model.define_doublet()    # find the doublet state


    # generate outputs
    for n in range(num_models+1):
        with open('barcodes_{}.csv'.format(n), 'w') as myfile:
            for item in model.assigned[n]:
                myfile.write(str(item) + '\n')
        with open('initial_{}.csv'.format(n), 'w') as myfile:
            for item in model.initial[n-1]:
                myfile.write(str(item) + '\n')
    with open('sc_split.log', 'a') as myfile: myfile.write('doublet: ' + str(model.doublet) + '\n' + 'ML: ' + str(max_likelihood) + '\n')

if __name__ == '__main__':
    main()
